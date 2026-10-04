// Админка без перезагрузок: формы уходят через fetch,
// а обновляется только та секция страницы, которую затронуло действие.
(function () {
  const ui = window.MKUI || {
    showToast: (message) => console.log(message),
    confirmDialog: (message) => Promise.resolve(window.confirm(message)),
  };

  const COLLAPSE_PREFIX = "mk-admin-collapsed:";

  const readCollapsed = (key) => {
    try {
      return window.localStorage.getItem(COLLAPSE_PREFIX + key) === "1";
    } catch (error) {
      return false;
    }
  };

  const writeCollapsed = (key, collapsed) => {
    try {
      window.localStorage.setItem(COLLAPSE_PREFIX + key, collapsed ? "1" : "0");
    } catch (error) {
      /* приватный режим — просто не запоминаем */
    }
  };

  const applyCollapsed = (block, collapsed) => {
    block.classList.toggle("is-collapsed", collapsed);
    const toggle = block.querySelector("[data-collapse-toggle]");
    if (toggle) toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  };

  const initCollapsibles = () => {
    document.querySelectorAll("[data-collapse]").forEach((block) => {
      const key = block.dataset.collapse;
      applyCollapsed(block, readCollapsed(key));
      if (block.dataset.collapseReady === "1") return;
      block.dataset.collapseReady = "1";
      const toggle = block.querySelector("[data-collapse-toggle]");
      if (!toggle) return;
      toggle.addEventListener("click", () => {
        const collapsed = !block.classList.contains("is-collapsed");
        applyCollapsed(block, collapsed);
        writeCollapsed(key, collapsed);
      });
    });
  };

  const refreshSections = async (selectors) => {
    const response = await fetch(window.location.href, {
      headers: { "X-Requested-With": "fetch-page" },
      credentials: "same-origin",
    });
    if (!response.ok) return;
    const doc = new DOMParser().parseFromString(
      await response.text(),
      "text/html"
    );
    selectors.forEach((selector) => {
      const fresh = doc.querySelector(selector);
      const current = document.querySelector(selector);
      if (fresh && current) current.innerHTML = fresh.innerHTML;
    });
    initCollapsibles();
  };

  const setBusy = (form, busy) => {
    form.classList.toggle("is-busy", busy);
    form
      .querySelectorAll("button[type=submit]")
      .forEach((button) => (button.disabled = busy));
  };

  const submitForm = async (form) => {
    const refresh = form.dataset.refresh;
    setBusy(form, true);
    try {
      const response = await fetch(form.action, {
        method: (form.method || "post").toUpperCase(),
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin",
      });

      let payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        payload = null;
      }

      if (response.status === 401 || response.status === 403) {
        window.location.href = "/admin/login";
        return;
      }
      if (!response.ok || (payload && payload.ok === false)) {
        ui.showToast(
          (payload && payload.message) || "Не удалось сохранить",
          true
        );
        return;
      }

      ui.showToast((payload && payload.message) || "Сохранено");
      if (form.dataset.reset === "1" || form.action.endsWith("/users/bulk")) {
        form.reset();
      }
      if (refresh) {
        await refreshSections(refresh.split(",").map((part) => part.trim()));
      }
    } catch (error) {
      ui.showToast("Сеть недоступна. Попробуйте ещё раз.", true);
    } finally {
      setBusy(form, false);
    }
  };

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-ajax]");
    if (!form) return;
    event.preventDefault();
    if (form.classList.contains("is-busy")) return;

    const question = form.dataset.confirm;
    if (question && !(await ui.confirmDialog(question))) return;
    submitForm(form);
  });

  // Фильтры и постраничная навигация тоже без перезагрузки:
  // меняем адрес в истории и перерисовываем только нужную секцию.
  const goTo = async (url, selectors) => {
    window.history.pushState({}, "", url);
    await refreshSections(selectors);
  };

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-ajax-get]");
    if (!form) return;
    event.preventDefault();
    const params = new URLSearchParams(new FormData(form));
    const url = `${form.action}?${params.toString()}`;
    await goTo(url, (form.dataset.refresh || "#panel-orders").split(","));
  });

  document.addEventListener("click", async (event) => {
    const link = event.target.closest("a[data-ajax-link]");
    if (!link) return;
    event.preventDefault();
    await goTo(link.href, (link.dataset.refresh || "#panel-orders").split(","));
  });

  window.addEventListener("popstate", () => {
    refreshSections(["#panel-users", "#panel-orders", "#panel-products"]);
  });

  document.addEventListener("change", (event) => {
    const control = event.target.closest("[data-autosubmit]");
    if (!control) return;
    const form = control.closest("form[data-ajax]");
    if (form) submitForm(form);
  });

  initCollapsibles();
})();
