const formulario = document.getElementById("edicion-compra");
if (formulario) {
    const agregar = document.getElementById("agregar-item-edicion");
    const cantidad = document.getElementById("id_nuevos-TOTAL_FORMS");
    const maximo = document.getElementById("id_nuevos-MAX_NUM_FORMS");
    const siguiente = document.getElementById("siguiente-edicion");
    const anterior = document.getElementById("anterior-edicion");
    const guardar = document.getElementById("guardar-edicion");
    let paso = 1;
    const moneda = valor => "$ " + valor.toLocaleString("es-CO", {maximumFractionDigits: 2});
    function calcular() {
        let subtotal = 0;
        formulario.querySelectorAll(".item-edicion").forEach(fila => {
            if (!fila.querySelector('[name$="-retirar"]')?.checked) {
                subtotal += Number(fila.querySelector('[name$="-valor"]')?.value || 0);
            }
        });
        const iva = Number(formulario.elements.impuesto.value || 0);
        const descuento = Number(formulario.elements.descuento.value || 0);
        const total = subtotal + iva - descuento;
        [["subtotal", subtotal], ["iva", iva], ["descuento", descuento], ["total", total]].forEach(([nombre, valor]) => {
            document.getElementById("edicion-" + nombre).textContent = moneda(valor);
        });
        const valido = Number.isFinite(total) && subtotal > 0 && total > 0 && total <= 9999999999.99;
        document.getElementById("aviso-edicion").textContent = valido ? "Total calculado. El servidor verificará los cambios." : "Revisa los valores de la compra.";
        siguiente.disabled = !valido;
        agregar.disabled = Number(cantidad.value) >= Number(maximo.value);
        return valido;
    }
    function mostrarPaso(numero) {
        paso = numero;
        document.getElementById("paso-edicion").textContent = paso === 1 ? "Paso 1 de 2: datos de la compra" : "Paso 2 de 2: asignar gastos";
        document.getElementById("datos-edicion").hidden = paso === 2;
        document.getElementById("titulo-edicion-items").textContent = paso === 1 ? "Ítems" : "Asignar cada ítem";
        formulario.querySelectorAll(".item-edicion").forEach(fila => {
            const retirada = fila.querySelector('[name$="-retirar"]')?.checked;
            const descripcion = fila.querySelector('[name$="-descripcion"]')?.value;
            const valor = fila.querySelector('[name$="-valor"]')?.value;
            fila.hidden = paso === 2 && (retirada || (!descripcion && !valor));
            fila.querySelectorAll("p, div").forEach(campo => {
                if (campo.parentElement !== fila) return;
                const control = campo.querySelector("input, select");
                if (!control) return;
                const asignacion = /-(beneficiarios|destino|beneficiario)$/.test(control.name);
                campo.hidden = paso === 1 && asignacion;
            });
        });
        agregar.hidden = paso === 2;
        siguiente.hidden = paso === 2;
        anterior.hidden = paso === 1;
        guardar.hidden = paso === 1;
        calcular();
    }
    agregar.addEventListener("click", () => {
        const indice = Number(cantidad.value);
        if (indice >= Number(maximo.value)) return;
        const plantilla = document.getElementById("nuevo-item");
        document.getElementById("nuevos-items").insertAdjacentHTML("beforeend", plantilla.innerHTML.replace(/__prefix__/g, indice));
        cantidad.value = indice + 1;
        if (!siguiente.hidden) mostrarPaso(1);
        calcular();
    });
    formulario.addEventListener("input", calcular);
    formulario.addEventListener("change", calcular);
    if (!formulario.querySelector(".errorlist, .field-error, .form-error")) {
        mostrarPaso(1);
        siguiente.addEventListener("click", () => {
            const incorrecto = Array.from(formulario.elements).find(campo => campo.willValidate && !campo.closest("[hidden]") && !campo.checkValidity());
            if (incorrecto) { incorrecto.reportValidity(); return; }
            for (const fila of formulario.querySelectorAll(".item-edicion")) {
                if (fila.querySelector('[name$="-retirar"]')?.checked) continue;
                const descripcion = fila.querySelector('[name$="-descripcion"]');
                const valor = fila.querySelector('[name$="-valor"]');
                if (!descripcion || !valor || (!descripcion.value.trim() && !valor.value)) continue;
                if (!descripcion.value.trim() || !valor.value || Number(valor.value) <= 0) {
                    const campo = !descripcion.value.trim() ? descripcion : valor;
                    campo.setCustomValidity("Completa la descripción y el valor positivo del ítem.");
                    campo.reportValidity();
                    campo.addEventListener("input", () => campo.setCustomValidity(""), {once: true});
                    return;
                }
            }
            if (calcular()) mostrarPaso(2);
        });
        anterior.addEventListener("click", () => mostrarPaso(1));
        formulario.addEventListener("submit", evento => {
            if (paso === 1) { evento.preventDefault(); siguiente.click(); }
        });
        formulario.addEventListener("invalid", evento => {
            if (evento.target.closest("[hidden]")) mostrarPaso(1);
        }, true);
    }
    formulario.addEventListener("submit", evento => {
        if (!evento.defaultPrevented) guardar.disabled = true;
    });
    window.addEventListener("pageshow", () => guardar.disabled = false);
    calcular();
}
