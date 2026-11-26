from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from auditlog.services import registrar_cambio
from expenses.models import Grupo, Membresia
from expenses.services.permisos import exigir_miembro, es_administrador
from ledger.models import Compensacion, AprobacionCompensacion, TramoCompensacion, Obligacion, AplicacionPago
from ledger.services.obligaciones import _validar_monto
from ledger.services.simplificacion import buscar_cadena


@transaction.atomic
def solicitar_compensacion(usuario, grupo_id, deudor_id, acreedor_id, monto, clave):
    grupo = Grupo.objects.select_for_update().get(pk=grupo_id)
    exigir_miembro(grupo_id, usuario)
    if grupo.archivado:
        raise ValidationError("El grupo está archivado.")
    if usuario.pk != deudor_id and not es_administrador(grupo_id, usuario):
        raise PermissionDenied("Solo el deudor o un administrador puede solicitar la compensación.")
    monto = _validar_monto(monto)
    anterior = Compensacion.objects.filter(clave=clave).first()
    if anterior:
        if (anterior.grupo_id, anterior.solicitante_id, anterior.deudor_id, anterior.acreedor_id, anterior.monto) != (grupo_id, usuario.pk, deudor_id, acreedor_id, monto):
            raise ValidationError("La clave ya pertenece a otra solicitud.")
        return anterior
    if Compensacion.objects.filter(grupo=grupo, deudor_id=deudor_id, acreedor_id=acreedor_id, estado__in=["pendiente", "aprobada"]).exists():
        raise ValidationError("Ya existe una solicitud activa entre estas personas.")
    obligaciones = list(Obligacion.objects.select_for_update().filter(
        grupo=grupo, anulada=False, asignacion__anulada=False,
        asignacion__item__anulada=False, asignacion__item__compra__anulada=False,
    ).exclude(asignacion__item__compra__revisiones__estado="objetada").order_by("pk"))
    ids = [obligacion.pk for obligacion in obligaciones]
    reservas = dict(AplicacionPago.objects.filter(
        obligacion_id__in=ids, anulada=False, pago__anulada=False,
        pago__estado__in=["pendiente", "confirmado"],
    ).values("obligacion_id").annotate(total=Sum("monto")).values_list("obligacion_id", "total"))
    for identificador, total in TramoCompensacion.objects.filter(
        obligacion_id__in=ids, compensacion__estado__in=["pendiente", "aprobada", "aplicada"],
    ).values("obligacion_id").annotate(total=Sum("monto")).values_list("obligacion_id", "total"):
        reservas[identificador] = reservas.get(identificador, Decimal("0")) + total
    montos = {}
    por_pareja = {}
    for obligacion in obligaciones:
        disponible = obligacion.monto - reservas.get(obligacion.pk, Decimal("0"))
        if disponible > 0:
            pareja = (obligacion.deudor_id, obligacion.acreedor_id)
            montos[pareja] = montos.get(pareja, Decimal("0")) + disponible
            por_pareja.setdefault(pareja, []).append((obligacion, disponible))
    disponibles = [{"deudor_id": a, "acreedor_id": b, "monto": valor}
                   for (a, b), valor in montos.items() if (a, b) != (deudor_id, acreedor_id)]
    cadena = buscar_cadena(disponibles, deudor_id, acreedor_id, monto)
    if len(cadena) < 3:
        raise ValidationError("No existe una cadena indirecta disponible para este monto.")
    integrantes = set(Membresia.objects.filter(grupo=grupo, activo=True).values_list("usuario_id", flat=True))
    integrantes.add(grupo.creador_id)
    if not set(cadena).issubset(integrantes):
        raise ValidationError("Todos los participantes deben pertenecer al grupo.")
    compensacion = Compensacion.objects.create(
        grupo=grupo, solicitante=usuario, deudor_id=deudor_id,
        acreedor_id=acreedor_id, monto=monto, clave=clave,
    )
    AprobacionCompensacion.objects.bulk_create([
        AprobacionCompensacion(compensacion=compensacion, usuario_id=persona)
        for persona in cadena
    ])
    tramos = []
    for orden, pareja in enumerate(zip(cadena, cadena[1:]), 1):
        restante = monto
        for obligacion, disponible in por_pareja[pareja]:
            valor = min(restante, disponible)
            tramos.append(TramoCompensacion(compensacion=compensacion, obligacion=obligacion, orden=orden, monto=valor))
            restante -= valor
            if restante == 0:
                break
        if restante:
            raise ValidationError("La cadena ya no dispone del monto solicitado.")
    TramoCompensacion.objects.bulk_create(tramos)
    registrar_cambio(usuario, compensacion, "solicitar", {"cadena": cadena, "monto": str(monto)})
    return compensacion


@transaction.atomic
def responder_compensacion(usuario, grupo_id, compensacion_id, aceptar):
    grupo = Grupo.objects.select_for_update().get(pk=grupo_id)
    exigir_miembro(grupo_id, usuario)
    if grupo.archivado:
        raise ValidationError("El grupo está archivado.")
    compensacion = Compensacion.objects.select_for_update().filter(pk=compensacion_id, grupo=grupo).first()
    if compensacion is None or compensacion.estado != "pendiente":
        raise ValidationError("La solicitud no está pendiente.")
    aprobacion = compensacion.aprobaciones.filter(usuario=usuario, estado="pendiente").first()
    if aprobacion is None:
        raise PermissionDenied("No tienes una aprobación pendiente para esta solicitud.")
    aprobacion.estado = "aceptada" if aceptar else "rechazada"
    aprobacion.fecha_respuesta = timezone.now()
    aprobacion.save(update_fields=["estado", "fecha_respuesta"])
    if not aceptar:
        compensacion.estado = "rechazada"
    elif not compensacion.aprobaciones.exclude(estado="aceptada").exists():
        compensacion.estado = "aprobada"
    compensacion.save(update_fields=["estado"])
    registrar_cambio(usuario, compensacion, aprobacion.estado, {"estado": compensacion.estado})
    return compensacion
