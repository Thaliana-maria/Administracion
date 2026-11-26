document.addEventListener("DOMContentLoaded", function () {
    const formulario = document.getElementById("purchase-form");
    const totalElemento = document.getElementById("purchase-total");

    if (!formulario || !totalElemento) {
        return;
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