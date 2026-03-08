(function () {
  "use strict";

  const API = "/api";

  function apiFetch(url, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    return fetch(url, opts).then(function (r) {
      if (r.status === 401) {
        window.location.href = "/login";
        return Promise.reject(new Error("Login required"));
      }
      return r;
    });
  }

  function formatMoney(n) {
    return "$" + Number(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function formatPriceAsOf(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
    } catch (e) {
      return "";
    }
  }

  function getSummary() {
    return apiFetch(API + "/summary").then((r) => r.json());
  }

  function refreshSummary() {
    getSummary().then(function (s) {
      document.getElementById("totalSpend").textContent = formatMoney(s.total);
      document.getElementById("itemCount").textContent = s.item_count;
      document.getElementById("todosLeft").textContent = s.todos_left;
    });
  }

  // ----- Shopping items (to buy) -----
  function loadItems() {
    return apiFetch(API + "/items").then((r) => r.json());
  }

  function loadAcquiredItems() {
    return apiFetch(API + "/items?acquired=true").then((r) => r.json());
  }

  function setItemAcquired(id, acquired) {
    return apiFetch(API + "/items/" + id + "/acquired", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acquired: acquired }),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to update");
      return r.json();
    });
  }

  function fetchPriceFromUrl(url) {
    if (!url || !url.trim()) return Promise.reject(new Error("Enter a product link first"));
    return apiFetch(API + "/fetch-price?url=" + encodeURIComponent(url.trim())).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.error || "Could not fetch price");
        return data;
      });
    });
  }

  function addItem(data) {
    return apiFetch(API + "/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to add item");
      return r.json();
    });
  }

  function setFetchPriceState(btn, loading) {
    btn.disabled = loading;
    btn.textContent = loading ? "Fetching…" : "Fetch price";
  }

  function updateItem(id, data) {
    return apiFetch(API + "/items/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to update");
      return r.json();
    });
  }

  function deleteItem(id) {
    return apiFetch(API + "/items/" + id, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error("Failed to delete");
    });
  }

  function renderItems(items) {
    const list = document.getElementById("shoppingList");
    const tpl = document.getElementById("itemRow");
    list.innerHTML = "";
    list.classList.toggle("empty", !items.length);

    var latestPriceDate = null;
    items.forEach(function (item) {
      if (item.price_updated_at && (!latestPriceDate || item.price_updated_at > latestPriceDate)) {
        latestPriceDate = item.price_updated_at;
      }
    });
    var summaryEl = document.getElementById("pricesAsOfSummary");
    if (latestPriceDate) {
      summaryEl.textContent = "Prices as of " + formatPriceAsOf(latestPriceDate);
      summaryEl.classList.add("visible");
    } else {
      summaryEl.textContent = "";
      summaryEl.classList.remove("visible");
    }

    items.forEach(function (item) {
      const li = tpl.content.cloneNode(true).querySelector("li");
      li.dataset.id = item.id;
      li.querySelector(".item-name").textContent = item.name;
      li.querySelector(".item-price").textContent = formatMoney(item.price * item.qty);
      const priceAsOfEl = li.querySelector(".item-price-as-of");
      if (item.price_updated_at) {
        priceAsOfEl.textContent = "Price as of " + formatPriceAsOf(item.price_updated_at);
        priceAsOfEl.classList.add("has-date");
      }
      li.querySelector(".item-qty").textContent = "×" + item.qty;
      if (item.shipping_estimate) {
        li.querySelector(".item-shipping").textContent = item.shipping_estimate;
        li.querySelector(".item-shipping").classList.add("has-shipping");
      }

      const linkWrap = li.querySelector(".item-link-wrap");
      if (item.link) {
        const a = document.createElement("a");
        a.href = item.link;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "link-btn";
        a.textContent = "View Item";
        linkWrap.appendChild(a);
      }

      li.querySelector(".btn-bought").addEventListener("click", function () {
        setItemAcquired(item.id, true).then(function () {
          loadItems().then(renderItems);
          loadAcquiredItems().then(renderAcquired);
          refreshSummary();
        });
      });
      li.querySelector(".btn-edit").addEventListener("click", function () {
        editItem(item, li);
      });
      li.querySelector(".btn-delete").addEventListener("click", function () {
        deleteItem(item.id).then(function () {
          loadItems().then(renderItems);
          refreshSummary();
        });
      });
      list.appendChild(li);
    });
  }

  function renderAcquired(items) {
    const list = document.getElementById("acquiredList");
    const tpl = document.getElementById("acquiredRow");
    list.innerHTML = "";
    list.classList.toggle("empty", !items.length);

    items.forEach(function (item) {
      const li = tpl.content.cloneNode(true).querySelector("li");
      li.dataset.id = item.id;
      li.querySelector(".item-name").textContent = item.name;
      li.querySelector(".item-price").textContent = formatMoney(item.price * item.qty);
      const priceAsOfEl = li.querySelector(".item-price-as-of");
      if (item.price_updated_at) {
        priceAsOfEl.textContent = "Price as of " + formatPriceAsOf(item.price_updated_at);
        priceAsOfEl.classList.add("has-date");
      }
      li.querySelector(".item-qty").textContent = "×" + item.qty;
      if (item.shipping_estimate) {
        li.querySelector(".item-shipping").textContent = item.shipping_estimate;
        li.querySelector(".item-shipping").classList.add("has-shipping");
      }

      const linkWrap = li.querySelector(".item-link-wrap");
      if (item.link) {
        const a = document.createElement("a");
        a.href = item.link;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "link-btn";
        a.textContent = "View Item";
        linkWrap.appendChild(a);
      }
      list.appendChild(li);
    });
  }

  function editItem(item, li) {
    const nameEl = li.querySelector(".item-name");
    const priceEl = li.querySelector(".item-price");
    const qtyEl = li.querySelector(".item-qty");
    const linkWrap = li.querySelector(".item-link-wrap");
    const actions = li.querySelector(".item-actions");

    const form = document.createElement("form");
    form.className = "form form-inline";
    form.innerHTML =
      '<input type="text" name="name" value="' +
      escapeHtml(item.name) +
      '" required />' +
      '<input type="number" name="price" value="' +
      item.price +
      '" step="0.01" min="0" required />' +
      '<input type="number" name="qty" value="' +
      item.qty +
      '" min="1" />' +
      '<input type="url" name="link" value="' +
      escapeHtml(item.link || "") +
      '" placeholder="Link (optional)" />' +
      '<input type="text" name="shipping_estimate" value="' +
      escapeHtml(item.shipping_estimate || "") +
      '" placeholder="Shipping (optional)" />' +
      '<button type="submit">Save</button><button type="button" class="btn-cancel">Cancel</button>';

    nameEl.style.display = "none";
    priceEl.style.display = "none";
    li.querySelector(".item-price-as-of").style.display = "none";
    qtyEl.style.display = "none";
    li.querySelector(".item-shipping").style.display = "none";
    linkWrap.style.display = "none";
    actions.style.display = "none";
    li.insertBefore(form, nameEl);

    form.querySelector(".btn-cancel").addEventListener("click", function () {
      form.remove();
      nameEl.style.display = "";
      priceEl.style.display = "";
      li.querySelector(".item-price-as-of").style.display = "";
      qtyEl.style.display = "";
      li.querySelector(".item-shipping").style.display = "";
      linkWrap.style.display = "";
      actions.style.display = "";
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const fd = new FormData(form);
      updateItem(item.id, {
        name: fd.get("name"),
        price: parseFloat(fd.get("price")) || 0,
        qty: parseInt(fd.get("qty"), 10) || 1,
        link: fd.get("link") || null,
        shipping_estimate: fd.get("shipping_estimate") || null,
      }).then(function () {
        loadItems().then(renderItems);
        refreshSummary();
      });
    });
  }

  function escapeHtml(s) {
    if (!s) return "";
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  document.getElementById("addItemForm").addEventListener("submit", function (e) {
    e.preventDefault();
    const form = this;
    const fd = new FormData(form);
    const payload = {
      name: fd.get("name"),
      price: parseFloat(fd.get("price")) || 0,
      qty: parseInt(fd.get("qty"), 10) || 1,
      link: fd.get("link") || null,
      shipping_estimate: fd.get("shipping_estimate") || null,
    };
    if (form.dataset.priceUpdatedAt) {
      payload.price_updated_at = form.dataset.priceUpdatedAt;
    }
    addItem(payload).then(function () {
      form.reset();
      form.querySelector("[name=qty]").value = 1;
      delete form.dataset.priceUpdatedAt;
      loadItems().then(renderItems);
      refreshSummary();
    });
  });

  document.getElementById("fetchPriceBtn").addEventListener("click", function () {
    const form = document.getElementById("addItemForm");
    const linkInput = form.querySelector('[name="link"]');
    const priceInput = form.querySelector('[name="price"]');
    const btn = this;
    setFetchPriceState(btn, true);
    fetchPriceFromUrl(linkInput.value)
      .then(function (data) {
        priceInput.value = data.price;
        form.dataset.priceUpdatedAt = new Date().toISOString();
        setFetchPriceState(btn, false);
      })
      .catch(function (err) {
        setFetchPriceState(btn, false);
        alert(err.message || "Could not fetch price from that link.");
      });
  });

  document.getElementById("refreshAllPricesBtn").addEventListener("click", function () {
    const btn = this;
    btn.disabled = true;
    btn.textContent = "Updating…";
    apiFetch(API + "/items/refresh-prices", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        btn.textContent = "Update all prices";
        loadItems().then(renderItems);
        refreshSummary();
        var summaryEl = document.getElementById("pricesAsOfSummary");
        if (data.updated > 0) {
          summaryEl.textContent = "Prices as of " + formatPriceAsOf(data.prices_as_of);
          summaryEl.classList.add("visible");
        }
        if (data.failed > 0 && data.updated === 0) {
          alert("Could not fetch prices from any of the links. Try checking the URLs or update prices manually.");
        } else if (data.failed > 0) {
          alert("Updated " + data.updated + " price(s). " + data.failed + " link(s) could not be updated.");
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.textContent = "Update all prices";
        alert("Something went wrong updating prices.");
      });
  });

  // ----- Todos -----
  let todoFilter = "all";

  function loadTodos() {
    return apiFetch(API + "/todos").then(function (r) { return r.json(); });
  }

  function addTodo(data) {
    return apiFetch(API + "/todos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: data.title }),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to add");
      return r.json();
    });
  }

  function setTodoDone(id, done) {
    return apiFetch(API + "/todos/" + id, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done: done }),
    }).then((r) => {
      if (!r.ok) throw new Error("Failed to update");
      return r.json();
    });
  }

  function deleteTodo(id) {
    return apiFetch(API + "/todos/" + id, { method: "DELETE" }).then(function (r) {
      if (!r.ok) throw new Error("Failed to delete");
    });
  }

  function renderTodos(todos) {
    const list = document.getElementById("todoList");
    const tpl = document.getElementById("todoRow");
    list.innerHTML = "";
    list.classList.toggle("empty", !todos.length);

    todos.forEach(function (t) {
      const li = tpl.content.cloneNode(true).querySelector("li");
      li.dataset.id = t.id;
      if (t.done) li.classList.add("done");
      const show =
        todoFilter === "all" ||
        (todoFilter === "active" && !t.done) ||
        (todoFilter === "done" && t.done);
      if (!show) li.classList.add("hidden");

      const title = li.querySelector(".todo-title");
      title.textContent = t.title;
      const cb = li.querySelector(".todo-checkbox");
      cb.checked = !!t.done;

      cb.addEventListener("change", function () {
        setTodoDone(t.id, cb.checked).then(function (updated) {
          li.classList.toggle("done", !!updated.done);
          refreshSummary();
        });
      });

      li.querySelector(".btn-delete").addEventListener("click", function () {
        deleteTodo(t.id).then(function () {
          loadTodos().then(renderTodos);
          refreshSummary();
        });
      });

      list.appendChild(li);
    });
  }

  document.getElementById("addTodoForm").addEventListener("submit", function (e) {
    e.preventDefault();
    const fd = new FormData(this);
    const title = fd.get("title");
    if (!title.trim()) return;
    addTodo({ title: title.trim() }).then(function () {
      this.reset();
      loadTodos().then(renderTodos);
      refreshSummary();
    }.bind(this));
  });

  document.querySelectorAll(".filter-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".filter-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      todoFilter = btn.dataset.filter;
      loadTodos().then(renderTodos);
    });
  });

  // ----- Nav -----
  document.querySelectorAll(".nav-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const panelId = "panel-" + btn.dataset.panel;
      document.querySelectorAll(".nav-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      document.querySelectorAll(".panel").forEach(function (p) {
        p.classList.toggle("active", p.id === panelId);
      });
      if (btn.dataset.panel === "acquired") {
        loadAcquiredItems().then(renderAcquired);
      }
    });
  });

  // ----- PWA: register service worker -----
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  // ----- Init -----
  loadItems().then(renderItems);
  loadAcquiredItems().then(renderAcquired);
  loadTodos().then(renderTodos);
  refreshSummary();
})();
