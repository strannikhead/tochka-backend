const DEFAULT_PRODUCT_ID = "770e8400-e29b-41d4-a716-446655440002";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const API_PREFIX = API_BASE_URL ? API_BASE_URL.replace(/\/$/, "") : "";

const params = new URLSearchParams(window.location.search);
const skuParam = params.get("sku");
const productId = params.get("id") || DEFAULT_PRODUCT_ID;

const root = document.querySelector("#app");
root.innerHTML = `
  <header>
    <a href="/">← назад</a>
  </header>
  <main>
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

function formatPrice(value) {
  return new Intl.NumberFormat("ru-RU").format(value / 100) + " ₽";
}

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
