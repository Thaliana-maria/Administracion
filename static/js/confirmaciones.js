document.addEventListener("click", function (evento) {
    const enlace = evento.target.closest("a[data-confirmacion]");
    if (!enlace || !window.HTMLDialogElement || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
    const ventana = document.getElementById("ventana-confirmacion");
    if (!ventana || typeof ventana.showModal !== "function") return;
    evento.preventDefault();
    ventana.querySelector("h2").textContent = enlace.dataset.confirmacion;
    ventana.querySelector("p").textContent = enlace.dataset.aviso;
    ventana.querySelector("form").action = enlace.href;
    ventana.showModal();
});
document.addEventListener("click", function (evento) {
    if (evento.target.id === "cancelar-confirmacion") {
        document.getElementById("ventana-confirmacion").close();
    }
});
