document.addEventListener("click", function (evento) {
    const enlace = evento.target.closest("a[data-confirmacion]");
    if (!enlace || !window.HTMLDialogElement || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
    const ventana = document.getElementById("ventana-confirmacion");
    if (!ventana || typeof ventana.showModal !== "function") return;
    evento.preventDefault();
    ventana.querySelector("h2").textContent = enlace.dataset.confirmacion;
    ventana.querySelector("p").textContent = enlace.dataset.aviso;
    ventana.querySelector("form").action = enlace.href;
    ventana.querySelectorAll("[data-dato-confirmacion]").forEach(campo => campo.remove());
    ventana.querySelector("button[type=submit]").textContent = "Confirmar anulación";
    ventana.showModal();
});
document.addEventListener("click", function (evento) {
    if (evento.target.id === "cancelar-confirmacion") {
        document.getElementById("ventana-confirmacion").close();
    }
});

document.addEventListener("submit", function (evento) {
    const formulario = evento.target;
    if (!formulario.matches("form[data-confirmacion]")) return;
    const ventana = document.getElementById("ventana-confirmacion");
    if (!ventana || typeof ventana.showModal !== "function") return;
    evento.preventDefault();
    ventana.querySelector("h2").textContent = formulario.dataset.confirmacion;
    ventana.querySelector("p").textContent = formulario.dataset.aviso;
    const destino = ventana.querySelector("form");
    destino.action = formulario.action;
    destino.querySelectorAll("[data-dato-confirmacion]").forEach(campo => campo.remove());
    const datos = new FormData(formulario);
    if (evento.submitter?.name) datos.append(evento.submitter.name, evento.submitter.value);
    for (const [nombre, valor] of datos) {
        if (nombre === "csrfmiddlewaretoken" || nombre === "confirmar" || typeof valor !== "string") continue;
        const campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = nombre;
        campo.value = valor;
        campo.dataset.datoConfirmacion = "";
        destino.appendChild(campo);
    }
    ventana.querySelector("button[type=submit]").textContent = formulario.dataset.boton || "Confirmar";
    ventana.showModal();
});
