document.addEventListener("DOMContentLoaded", function () {
    const formulario = document.getElementById("purchase-form");
    const totalElemento = document.getElementById("purchase-total");

    if (!formulario || !totalElemento) {
        return;
    }

    function compararNombres(a, b) {
        const primero = Array.from(a.text.toLowerCase(), letra => letra.codePointAt(0));
        const segundo = Array.from(b.text.toLowerCase(), letra => letra.codePointAt(0));
        for (let i = 0; i < Math.min(primero.length, segundo.length); i++) {
            if (primero[i] !== segundo[i]) return primero[i] - segundo[i];
        }
        return primero.length - segundo.length;
    }

    function mostrarReparto() {
        const contenedor = document.getElementById("partes-compra");
        const pagador = formulario.elements["pagador"];
        if (!contenedor || !pagador) return;
        const personas = Array.from(pagador.options).filter(opcion => opcion.value);
        const partes = new Map(personas.map(persona => [persona.value, 0]));
        const orden = personas.slice().sort((a, b) => {
            if (a.value === b.value) return 0;
            if (a.value === pagador.value) return -1;
            if (b.value === pagador.value) return 1;
            return compararNombres(a, b) || Number(a.value) - Number(b.value);
        });
        let incompleto = false;
        formulario.querySelectorAll(".purchase-item").forEach(fila => {
            const valor = Number(fila.querySelector('[name$="-valor"]')?.value || 0);
            const destino = fila.querySelector('[name$="-destino"]')?.value;
            const beneficiario = fila.querySelector('[name$="-beneficiario"]')?.value;
            if (!Number.isSafeInteger(valor) || valor <= 0 || !orden.length) return;
            if (destino === "persona") {
                if (!partes.has(beneficiario)) { incompleto = true; return; }
                partes.set(beneficiario, partes.get(beneficiario) + valor);
            } else {
                const base = Math.floor(valor / orden.length);
                const sobrante = valor % orden.length;
                if (base === 0) incompleto = true;
                orden.forEach((persona, indice) => partes.set(persona.value, partes.get(persona.value) + base + (indice < sobrante ? 1 : 0)));
            }
        });
        const subtotal = Array.from(partes.values()).reduce((suma, valor) => suma + valor, 0);
        const ajuste = Math.round(Number(formulario.elements["impuesto"]?.value || 0) * 100) -
            Math.round(Number(formulario.elements["descuento"]?.value || 0) * 100);
        const cuotas = new Map();
        if (subtotal > 0 && Number.isSafeInteger(subtotal) && Number.isSafeInteger(ajuste) && !incompleto) {
            const magnitud = BigInt(Math.abs(ajuste));
            const base = BigInt(subtotal);
            const residuos = personas.filter(persona => partes.get(persona.value) > 0).map(persona => {
                const producto = magnitud * BigInt(partes.get(persona.value));
                cuotas.set(persona.value, Number(producto / base));
                return {persona, residuo: producto % base};
            });
            residuos.sort((a, b) => a.residuo === b.residuo
                ? compararNombres(a.persona, b.persona) || Number(a.persona.value) - Number(b.persona.value)
                : a.residuo > b.residuo ? -1 : 1);
            const sobrante = Math.abs(ajuste) - Array.from(cuotas.values()).reduce((suma, valor) => suma + valor, 0);
            residuos.slice(0, sobrante).forEach(({persona}) => cuotas.set(persona.value, cuotas.get(persona.value) + 1));
        }
        contenedor.replaceChildren();
        personas.forEach(persona => {
            const fila = document.createElement("p");
            const base = partes.get(persona.value);
            const ajustePersona = Number.isSafeInteger(ajuste) ? Math.sign(ajuste) * (cuotas.get(persona.value) || 0) / 100 : 0;
            fila.textContent = persona.text + ": $ " + (base + ajustePersona).toLocaleString("es-CO", {maximumFractionDigits: 2}) +
                (ajustePersona ? " (ajuste: " + ajustePersona.toLocaleString("es-CO", {maximumFractionDigits: 2}) + ")" : "");
            contenedor.appendChild(fila);
        });
        if (incompleto) {
            const aviso = document.createElement("p");
            aviso.textContent = "Revisa los beneficiarios y los valores: cada asignación debe ser de al menos un peso.";
            contenedor.appendChild(aviso);
        }
    }

    function calcularTotal() {
        const camposValor = formulario.querySelectorAll(
            'input[name$="-valor"]'
        );

        let total = 0;

        camposValor.forEach(function (campo) {
            const valor = parseFloat(campo.value);

            if (!isNaN(valor)) {
                total += valor;
            }
        });

        const impuesto = Number(formulario.elements["impuesto"]?.value || 0);
        const descuento = Number(formulario.elements["descuento"]?.value || 0);
        total += impuesto - descuento;
        const esperado = formulario.elements["total_esperado"];
        if (esperado) {
            esperado.setCustomValidity(esperado.value && Math.round(Number(esperado.value) * 100) !== Math.round(total * 100) ? "El total no coincide con los ítems, IVA y descuento." : "");
        }
        const verificacion = document.getElementById("verificacion-total");
        if (verificacion) {
            const coincide = esperado && esperado.value && Math.round(Number(esperado.value) * 100) === Math.round(total * 100);
            verificacion.textContent = !esperado || !esperado.value ? "Indica el total del recibo para verificarlo." : coincide ? "El total coincide con el recibo." : "El total no coincide con el recibo.";
            verificacion.classList.toggle("field-error", Boolean(esperado && esperado.value && !coincide));
        }
        mostrarReparto();
        totalElemento.textContent = "$ " + total.toLocaleString(
            "es-CO",
            {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2
            }
        );
    }

    formulario.addEventListener("input", calcularTotal);
    formulario.addEventListener("change", calcularTotal);

    const agregar = document.getElementById("agregar-item");
    const plantilla = document.getElementById("plantilla-item");
    const cantidad = formulario.querySelector('input[name$="-TOTAL_FORMS"]');
    if (agregar && plantilla && cantidad) {
        agregar.addEventListener("click", function () {
            const indice = Number(cantidad.value);
            if (indice >= 100) return;
            const contenido = plantilla.innerHTML.replace(/__prefix__/g, String(indice));
            formulario.querySelector(".purchase-items").insertAdjacentHTML("beforeend", contenido);
            cantidad.value = indice + 1;
            const nuevo = formulario.querySelector(".purchase-items").lastElementChild;
            nuevo.querySelector("legend").textContent = "Ítem " + (indice + 1);
            agregar.disabled = indice + 1 >= 100;
            calcularTotal();
        });
    }
    formulario.addEventListener("submit", function () {
        formulario.querySelectorAll('button[type="submit"]').forEach(function (boton) {
            boton.disabled = true;
        });
    });
    window.addEventListener("pageshow", function () {
        formulario.querySelectorAll('button[type="submit"]').forEach(function (boton) {
            boton.disabled = false;
        });
    });
    const siguiente = document.getElementById("paso-siguiente");
    const anterior = document.getElementById("paso-anterior");
    const guardar = document.getElementById("guardar-compra");
    const tituloPaso = document.getElementById("paso-compra");
    let paso = 1;
    function mostrarPaso(numero) {
        paso = numero;
        const vista = document.getElementById("vista-reparto");
        if (vista) vista.hidden = paso !== 2;
        mostrarReparto();
        formulario.querySelectorAll(".purchase-item [data-campo]").forEach(function (campo) {
            const asignacion = ["destino", "beneficiario"].includes(campo.dataset.campo);
            campo.hidden = paso === 1 ? asignacion : !asignacion && campo.dataset.campo !== "descripcion";
        });
        siguiente.hidden = paso !== 1;
        anterior.hidden = paso !== 2;
        guardar.hidden = paso !== 2;
        if (agregar) agregar.hidden = paso !== 1;
        tituloPaso.textContent = paso === 1 ? "Paso 1 de 2: datos de la compra" : "Paso 2 de 2: asignar gastos";
    }
    if (siguiente && anterior && guardar && tituloPaso && !formulario.querySelector(".purchase-field .field-error, .form-error, .errorlist")) {
        mostrarPaso(1);
        siguiente.addEventListener("click", function () {
            if (formulario.reportValidity()) mostrarPaso(2);
        });
        anterior.addEventListener("click", function () { mostrarPaso(1); });
        formulario.addEventListener("submit", function (evento) {
            if (paso === 1) {
                evento.preventDefault();
                guardar.disabled = false;
                mostrarPaso(2);
            }
        });
        if (agregar) agregar.addEventListener("click", function () { mostrarPaso(paso); });
    }
    calcularTotal();
});