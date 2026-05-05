const DEFAULT_PRODUCT_ID = "770e8400-e29b-41d4-a716-446655440002";
const DEFAULT_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const API_PREFIX = API_BASE_URL ? API_BASE_URL.replace(/\/$/, "") : "";

const params = new URLSearchParams(window.location.search);
const view = params.get("view") || "catalog";

const root = document.querySelector("#app");

function formatPrice(value) {
  return new Intl.NumberFormat("ru-RU").format(value / 100) + " ₽";
}

function renderTopbar(activeView) {
  const productLink = `?view=product&id=${params.get("id") || DEFAULT_PRODUCT_ID}`;
  const catalogLink = "?view=catalog";
  return `
    <header class="topbar">
      <div class="brand">NeoMarket</div>
      <nav class="topnav">
        <a class="${activeView === "catalog" ? "is-active" : ""}" href="${catalogLink}">Каталог</a>
        <a class="${activeView === "product" ? "is-active" : ""}" href="${productLink}">Карточка</a>
      </nav>
    </header>
  `;
}

function renderProductView() {
  const skuParam = params.get("sku");
  const productId = params.get("id") || DEFAULT_PRODUCT_ID;

  root.innerHTML = `
    ${renderTopbar("product")}
    <main class="product-view">
      <section class="gallery">
        <img id="mainImage" class="gallery__image" src="" alt="Фото товара" />
        <div id="thumbs" class="gallery__strip"></div>
      </section>

      <section class="details">
        <div class="details__card">
          <div id="status" class="status">Загружаем карточку...</div>
          <span id="discountBadge" class="badge" hidden>Скидка</span>
          <h1 id="productTitle" class="details__title"></h1>
          <p id="productDesc" class="details__desc"></p>
          <div class="price">
            <span id="currentPrice" class="price__current"></span>
            <span id="oldPrice" class="price__old" hidden></span>
          </div>
          <div class="actions">
            <button id="addToCart" class="btn btn--primary">В корзину</button>
            <button class="btn btn--ghost">В избранное</button>
          </div>
        </div>

        <div class="details__card">
          <h2>Вариации</h2>
          <div id="skuList" class="sku-list"></div>
        </div>

        <div class="details__card">
          <h2>Характеристики</h2>
          <div id="characteristics" class="characteristics"></div>
        </div>
      </section>
    </main>
  `;

  let product = null;
  let productImages = [];
  let selectedSkuId = skuParam;

  const gallery = document.getElementById("mainImage");
  const thumbs = document.getElementById("thumbs");
  const skuList = document.getElementById("skuList");
  const title = document.getElementById("productTitle");
  const description = document.getElementById("productDesc");
  const discountBadge = document.getElementById("discountBadge");
  const currentPrice = document.getElementById("currentPrice");
  const oldPrice = document.getElementById("oldPrice");
  const addToCart = document.getElementById("addToCart");
  const characteristics = document.getElementById("characteristics");
  const status = document.getElementById("status");

  function setStatus(message, isError = false) {
    status.textContent = message;
    status.classList.toggle("status--error", isError);
    status.hidden = !message;
  }

  function normalizeImages(images) {
    return (images || [])
      .map((image) => ({
        url: image.url,
        order: typeof image.order === "number" ? image.order : image.ordering || 0
      }))
      .sort((a, b) => a.order - b.order);
  }

  function setActiveImage(index) {
    const image = productImages[index] || productImages[0];
    if (!image) {
      return;
    }
    gallery.src = image.url;
    [...thumbs.children].forEach((thumb, idx) => {
      thumb.classList.toggle("gallery__thumb--active", idx === index);
    });
  }

  function renderGallery() {
    thumbs.innerHTML = "";
    productImages.forEach((image, idx) => {
      const thumb = document.createElement("img");
      thumb.src = image.url;
      thumb.alt = "Миниатюра";
      thumb.className = "gallery__thumb";
      thumb.addEventListener("click", () => setActiveImage(idx));
      thumbs.appendChild(thumb);
    });
    setActiveImage(0);
  }

  function renderCharacteristics() {
    characteristics.innerHTML = "";
    product.characteristics.forEach((item) => {
      const block = document.createElement("div");
      block.className = "characteristic";
      block.innerHTML = `
        <div class="characteristic__name">${item.name}</div>
        <div class="characteristic__value">${item.value}</div>
      `;
      characteristics.appendChild(block);
    });
  }

  function isSkuAvailable(sku) {
    if (typeof sku.in_stock === "boolean") {
      return sku.in_stock;
    }
    if (typeof sku.quantity === "number") {
      return sku.quantity > 0;
    }
    if (typeof sku.active_quantity === "number") {
      return sku.active_quantity > 0;
    }
    return false;
  }

  function skuImageUrl(sku) {
    if (sku.image) {
      return sku.image;
    }
    if (sku.images && sku.images.length > 0) {
      return sku.images[0].url;
    }
    return productImages[0]?.url || "";
  }

  function setSku(sku) {
    const isAvailable = isSkuAvailable(sku);
    const hasDiscount = sku.discount > 0;

    currentPrice.textContent = formatPrice(sku.price - sku.discount);
    oldPrice.hidden = !hasDiscount;
    discountBadge.hidden = !hasDiscount;
    if (hasDiscount) {
      oldPrice.textContent = formatPrice(sku.price);
    }

    addToCart.disabled = !isAvailable;
    addToCart.textContent = isAvailable ? "В корзину" : "Нет в наличии";

    const nextImage = skuImageUrl(sku);
    if (nextImage) {
      gallery.src = nextImage;
    }
  }

  function renderSkus() {
    skuList.innerHTML = "";
    product.skus.forEach((sku) => {
      const item = document.createElement("div");
      const isActive = sku.id === selectedSkuId;
      const isAvailable = isSkuAvailable(sku);

      item.className = `sku-item${isActive ? " sku-item--active" : ""}`;
      item.innerHTML = `
        <div>
          <div class="sku-item__name">${sku.name}</div>
          <div class="sku-item__meta">${sku.characteristics.map((c) => c.value).join(" · ")}</div>
        </div>
        <div class="sku-item__status${isAvailable ? "" : " sku-item__status--off"}">
          ${isAvailable ? "В наличии" : "Нет в наличии"}
        </div>
      `;

      item.addEventListener("click", () => {
        const nextParams = new URLSearchParams(window.location.search);
        nextParams.set("view", "product");
        nextParams.set("sku", sku.id);
        nextParams.set("id", product.id);
        history.replaceState(null, "", `?${nextParams.toString()}`);
        setSku(sku);
        renderSkus();
      });

      skuList.appendChild(item);
    });
  }

  async function loadProduct() {
    setStatus("Загружаем карточку...");
    try {
      const response = await fetch(`${API_PREFIX}/api/v1/products/${productId}`);
      if (response.status === 404) {
        setStatus("Товар недоступен. Вернитесь в каталог.", true);
        return;
      }
      if (response.status >= 500) {
        setStatus("Не удалось загрузить товар. Попробуйте позже.", true);
        return;
      }
      if (!response.ok) {
        setStatus("Ошибка загрузки карточки товара.", true);
        return;
      }

      product = await response.json();
    } catch (error) {
      setStatus("Не удалось подключиться к сервису B2C.", true);
      return;
    }

    productImages = normalizeImages(product.images);
    title.textContent = product.title;
    description.textContent = product.description;
    selectedSkuId = selectedSkuId || (product.skus[0] && product.skus[0].id);

    renderGallery();
    renderCharacteristics();
    renderSkus();

    const initialSku = product.skus.find((sku) => sku.id === selectedSkuId) || product.skus[0];
    if (initialSku) {
      setSku(initialSku);
    }

    setStatus("");
  }

  loadProduct();
}

function renderCatalogView() {
  root.innerHTML = `
    ${renderTopbar("catalog")}
    <main class="catalog-page">
      <section class="catalog-hero">
        <div>
          <p class="kicker">Категория</p>
          <h1>Смартфоны</h1>
          <p class="lead">Фильтруйте по брендам, цветам и сортируйте по цене или популярности.</p>
        </div>
        <div class="hero-card">
          <div class="hero-card__title">Доступные фасеты</div>
          <div class="hero-card__desc">Счётчики обновляются при каждом изменении фильтров.</div>
        </div>
      </section>

      <div class="catalog-layout">
        <aside class="catalog-sidebar">
          <div class="panel">
            <div class="panel__title">Фильтры</div>
            <div id="catalogStatus" class="status" hidden></div>
            <div id="facetList" class="filters"></div>
            <button id="clearFilters" class="btn btn--ghost btn--full">Сбросить фильтры</button>
          </div>
        </aside>

        <section class="catalog-results">
          <div class="catalog-toolbar">
            <div class="catalog-meta">
              <span id="resultCount">0 товаров</span>
              <span id="pageInfo" class="catalog-meta__page"></span>
            </div>
            <div class="catalog-controls">
              <input id="searchInput" class="input" placeholder="Поиск по названию" />
              <select id="sortSelect" class="select">
                <option value="rating">По рейтингу</option>
                <option value="popularity">По популярности</option>
                <option value="price_asc">Цена по возрастанию</option>
                <option value="price_desc">Цена по убыванию</option>
                <option value="date_desc">Сначала новые</option>
                <option value="discount_desc">Сначала со скидкой</option>
              </select>
            </div>
          </div>

          <div id="productGrid" class="product-grid"></div>

          <div class="pagination">
            <button id="prevPage" class="btn btn--ghost">Назад</button>
            <button id="nextPage" class="btn btn--primary">Вперёд</button>
          </div>
        </section>
      </div>
    </main>
  `;

  const facetList = document.getElementById("facetList");
  const productGrid = document.getElementById("productGrid");
  const resultCount = document.getElementById("resultCount");
  const pageInfo = document.getElementById("pageInfo");
  const sortSelect = document.getElementById("sortSelect");
  const searchInput = document.getElementById("searchInput");
  const prevPage = document.getElementById("prevPage");
  const nextPage = document.getElementById("nextPage");
  const clearFilters = document.getElementById("clearFilters");
  const catalogStatus = document.getElementById("catalogStatus");

  const state = {
    categoryId: DEFAULT_CATEGORY_ID,
    filters: {},
    sort: "rating",
    limit: 6,
    offset: 0,
    search: ""
  };

  let totalCount = 0;
  let pendingRequests = 0;

  function setCatalogStatus(message, isError = false) {
    catalogStatus.textContent = message;
    catalogStatus.classList.toggle("status--error", isError);
    catalogStatus.hidden = !message;
  }

  function markLoading(isLoading) {
    if (isLoading) {
      pendingRequests += 1;
      setCatalogStatus("Обновляем каталог...");
    } else {
      pendingRequests = Math.max(0, pendingRequests - 1);
      if (pendingRequests === 0) {
        setCatalogStatus("");
      }
    }
  }

  function buildQuery() {
    const searchValue = state.search.trim();
    const paramsList = [
      ["category_id", state.categoryId],
      ["limit", String(state.limit)],
      ["offset", String(state.offset)]
    ];
    if (state.sort) {
      paramsList.push(["sort", state.sort]);
    }
    if (searchValue.length >= 3) {
      paramsList.push(["search", searchValue]);
    }
    Object.entries(state.filters).forEach(([key, values]) => {
      values.forEach((value) => {
        paramsList.push([`filters[${key}]`, value]);
      });
    });
    return new URLSearchParams(paramsList).toString();
  }

  function buildFacetQuery() {
    const paramsList = [["category_id", state.categoryId]];
    Object.entries(state.filters).forEach(([key, values]) => {
      values.forEach((value) => {
        paramsList.push([`filters[${key}]`, value]);
      });
    });
    return new URLSearchParams(paramsList).toString();
  }

  function toggleFilter(key, value, checked) {
    const current = new Set(state.filters[key] || []);
    if (checked) {
      current.add(value);
    } else {
      current.delete(value);
    }
    if (current.size > 0) {
      state.filters[key] = Array.from(current);
    } else {
      delete state.filters[key];
    }
    state.offset = 0;
    loadCatalog();
  }

  function renderFacets(facets) {
    facetList.innerHTML = "";
    facets.forEach((facet) => {
      const group = document.createElement("div");
      group.className = "filter-group";
      group.innerHTML = `<div class="filter-group__title">${facet.name}</div>`;

      facet.values.forEach((item) => {
        const id = `filter-${facet.name}-${item.value}`;
        const option = document.createElement("label");
        const isChecked = (state.filters[facet.name] || []).includes(item.value);
        option.className = "filter-option";
        option.innerHTML = `
          <input id="${id}" type="checkbox" ${isChecked ? "checked" : ""} />
          <span>${item.value}</span>
          <span class="filter-option__count">${item.count}</span>
        `;
        const input = option.querySelector("input");
        input.addEventListener("change", (event) => {
          toggleFilter(facet.name, item.value, event.target.checked);
        });
        group.appendChild(option);
      });

      facetList.appendChild(group);
    });
  }

  function renderProducts(items) {
    productGrid.innerHTML = "";
    if (!items.length) {
      productGrid.innerHTML = `
        <div class="empty-state">
          <h3>Ничего не найдено</h3>
          <p>Попробуйте сбросить фильтры или изменить сортировку.</p>
        </div>
      `;
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "product-card";
      card.innerHTML = `
        <img src="${item.image}" alt="${item.title}" />
        <div class="product-card__body">
          <h3>${item.title}</h3>
          <div class="product-card__price">${formatPrice(item.price)}</div>
          <div class="product-card__meta">
            <span class="pill">${item.in_stock ? "В наличии" : "Нет в наличии"}</span>
            <span class="pill pill--muted">${item.is_in_cart ? "В корзине" : "Не в корзине"}</span>
          </div>
        </div>
      `;
      productGrid.appendChild(card);
    });
  }

  async function loadProducts() {
    markLoading(true);
    try {
      const response = await fetch(`${API_PREFIX}/api/v1/products?${buildQuery()}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || "Не удалось загрузить каталог");
      }
      const payload = await response.json();
      totalCount = payload.total_count || 0;
      renderProducts(payload.items || []);
      resultCount.textContent = `${totalCount} товаров`;
      const totalPages = Math.max(1, Math.ceil(totalCount / state.limit));
      const currentPage = Math.floor(state.offset / state.limit) + 1;
      pageInfo.textContent = `Страница ${currentPage} из ${totalPages}`;
      prevPage.disabled = state.offset === 0;
      nextPage.disabled = state.offset + state.limit >= totalCount;
    } catch (error) {
      setCatalogStatus(error.message, true);
      renderProducts([]);
    } finally {
      markLoading(false);
    }
  }

  async function loadFacets() {
    markLoading(true);
    try {
      const response = await fetch(`${API_PREFIX}/api/v1/catalog/facets?${buildFacetQuery()}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || "Не удалось загрузить фасеты");
      }
      const payload = await response.json();
      renderFacets(payload.facets || []);
    } catch (error) {
      setCatalogStatus(error.message, true);
      facetList.innerHTML = "";
    } finally {
      markLoading(false);
    }
  }

  async function loadCatalog() {
    await Promise.all([loadProducts(), loadFacets()]);
  }

  sortSelect.value = state.sort;
  sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    state.offset = 0;
    loadCatalog();
  });

  let searchTimeout = null;
  searchInput.addEventListener("input", (event) => {
    if (searchTimeout) {
      clearTimeout(searchTimeout);
    }
    searchTimeout = setTimeout(() => {
      state.search = event.target.value;
      state.offset = 0;
      loadCatalog();
    }, 350);
  });

  prevPage.addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit);
    loadCatalog();
  });

  nextPage.addEventListener("click", () => {
    state.offset = state.offset + state.limit;
    loadCatalog();
  });

  clearFilters.addEventListener("click", () => {
    state.filters = {};
    state.offset = 0;
    loadCatalog();
  });

  loadCatalog();
}

if (view === "product") {
  renderProductView();
} else {
  renderCatalogView();
}
