// Общие мелочи интерфейса: всплывающие сообщения и окно подтверждения.
(function () {
  const ensureToast = () => {
    let toast = document.getElementById("toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      toast.id = "toast";
      document.body.appendChild(toast);
    }
    return toast;
  };

  let hideTimer = null;
  const showToast = (message, isError = false) => {
    const toast = ensureToast();
    toast.textContent = message;
    toast.style.background = isError
      ? "rgba(217, 130, 43, 0.92)"
      : "rgba(28, 27, 24, 0.88)";
    toast.classList.add("toast--show");
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => toast.classList.remove("toast--show"), 3200);
  };

  const confirmDialog = (message, options = {}) =>
    new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.className = "modal-overlay";
      overlay.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true">
          <p class="modal__text"></p>
          <div class="modal__actions">
            <button class="btn modal__confirm" type="button"></button>
            <button class="ghost modal__cancel" type="button"></button>
          </div>
        </div>
      `;
      overlay.querySelector(".modal__text").textContent = message;
      overlay.querySelector(".modal__confirm").textContent =
        options.confirmText || "Да";
      overlay.querySelector(".modal__cancel").textContent =
        options.cancelText || "Отмена";

      const close = (result) => {
        document.removeEventListener("keydown", onKeyDown);
        overlay.classList.remove("modal-overlay--show");
        setTimeout(() => overlay.remove(), 150);
        resolve(result);
      };
      const onKeyDown = (event) => {
        if (event.key === "Escape") close(false);
        if (event.key === "Enter") close(true);
      };

      overlay
        .querySelector(".modal__confirm")
        .addEventListener("click", () => close(true));
      overlay
        .querySelector(".modal__cancel")
        .addEventListener("click", () => close(false));
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) close(false);
      });
      document.addEventListener("keydown", onKeyDown);

      document.body.appendChild(overlay);
      requestAnimationFrame(() =>
        overlay.classList.add("modal-overlay--show")
      );
      overlay.querySelector(".modal__confirm").focus();
    });

  window.MKUI = { showToast, confirmDialog };
})();
