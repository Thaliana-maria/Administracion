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
    calcularTotal();
});