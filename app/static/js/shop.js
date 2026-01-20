const toast = document.getElementById("toast");

const productCards = document.querySelectorAll(".product-card");
if (productCards.length) {
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries, target) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            target.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.2 }
    );
    productCards.forEach((card) => observer.observe(card));
  } else {
    productCards.forEach((card) => card.classList.add("is-visible"));
  }
}


const showToast = (message, isError = false) => {
  if (!toast) return;
  toast.textContent = message;
  toast.style.background = isError ? "rgba(217, 130, 43, 0.9)" : "rgba(28, 27, 24, 0.88)";
  toast.classList.add("toast--show");
  setTimeout(() => toast.classList.remove("toast--show"), 3200);
};

const updatePoints = (points) => {
  const value = document.querySelector(".pill__value");
  if (value) {
    value.textContent = `${points} баллов`;
  }
};

const buttons = document.querySelectorAll(".redeem-btn");
buttons.forEach((button) => {
  button.addEventListener("click", async () => {
    const variantId = button.dataset.variant;
    if (!variantId) return;
    button.disabled = true;
    const original = button.innerHTML;
    button.innerHTML = "Проверяем...";

    try {
      const response = await fetch("/api/redeem", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ variant_id: Number(variantId) }),
      });
      const payload = await response.json();
      if (!payload.ok) {
        showToast(payload.message || "Не удалось оформить заказ", true);
        return;
      }
      showToast(payload.message || "Готово!");
      if (typeof payload.points === "number") {
        updatePoints(payload.points);
      }
    } catch (error) {
      showToast("Сеть недоступна. Попробуйте позже.", true);
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  });
});