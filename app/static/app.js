// Show filename in file input label after selection
document.addEventListener("change", (e) => {
  if (e.target.type === "file" && e.target.classList.contains("hidden")) {
    const label = e.target.parentElement?.querySelector("span");
    if (label && e.target.files[0]) {
      label.textContent = e.target.files[0].name;
    }
  }
});

// HTMX: show loading state on scan button
document.addEventListener("htmx:beforeRequest", (e) => {
  const btn = e.detail.elt.querySelector("button[type=submit]");
  if (btn) btn.disabled = true;
});
document.addEventListener("htmx:afterRequest", (e) => {
  const btn = e.detail.elt.querySelector("button[type=submit]");
  if (btn) btn.disabled = false;
});
