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

    calcularTotal();
});