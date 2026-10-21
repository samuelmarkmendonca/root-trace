/**
 * ShopLite Stage 3: Real checkout and db backend wired via FastAPI proxy.
 * Real fetch() to /api/products and /api/checkout.
 */

// ---------------------------------------------------------------------------
// Schematic Category Icons
// ---------------------------------------------------------------------------
const CATEGORY_ICONS = {
  'Keyboards': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <rect x="2" y="4" width="20" height="16" rx="1"></rect>
    <line x1="6" y1="8" x2="6" y2="8.01"></line>
    <line x1="10" y1="8" x2="10" y2="8.01"></line>
    <line x1="14" y1="8" x2="14" y2="8.01"></line>
    <line x1="18" y1="8" x2="18" y2="8.01"></line>
    <line x1="6" y1="12" x2="6" y2="12.01"></line>
    <line x1="10" y1="12" x2="10" y2="12.01"></line>
    <line x1="14" y1="12" x2="14" y2="12.01"></line>
    <line x1="18" y1="12" x2="18" y2="12.01"></line>
    <line x1="8" y1="16" x2="16" y2="16"></line>
  </svg>`,
  'Peripherals': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <rect x="5" y="2" width="14" height="20" rx="4"></rect>
    <line x1="12" y1="6" x2="12" y2="10"></line>
  </svg>`,
  'Displays': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <rect x="2" y="3" width="20" height="14" rx="1"></rect>
    <line x1="8" y1="21" x2="16" y2="21"></line>
    <line x1="12" y1="17" x2="12" y2="21"></line>
  </svg>`,
  'Audio': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <path d="M3 18v-6a9 9 0 0 1 18 0v6"></path>
    <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"></path>
  </svg>`,
  'Hardware': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <rect x="2" y="7" width="20" height="10" rx="1"></rect>
    <line x1="6" y1="12" x2="8" y2="12"></line>
    <line x1="11" y1="12" x2="13" y2="12"></line>
    <line x1="16" y1="12" x2="18" y2="12"></line>
  </svg>`,
  'Accessories': `<svg class="schematic-svg" viewBox="0 0 24 24">
    <path d="M12 2v8"></path>
    <path d="M4 10h16"></path>
    <rect x="8" y="14" width="8" height="6" rx="1"></rect>
    <line x1="12" y1="10" x2="12" y2="14"></line>
  </svg>`
};

const DEFAULT_ICON = `<svg class="schematic-svg" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"></rect></svg>`;

// ---------------------------------------------------------------------------
// Product State (Live from backend API)
// ---------------------------------------------------------------------------
let PRODUCTS = [];
let currentFilter = null;

// ---------------------------------------------------------------------------
// Cart state
// ---------------------------------------------------------------------------
// cart = { [productId]: { product, qty } }
const cart = {};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(n) {
  return '$' + Number(n).toFixed(2);
}

function cartTotal() {
  return Object.values(cart).reduce((sum, { product, qty }) => sum + product.price * qty, 0);
}

function cartItemCount() {
  return Object.values(cart).reduce((sum, { qty }) => sum + qty, 0);
}

// ---------------------------------------------------------------------------
// Fetch & Render: Products
// ---------------------------------------------------------------------------
async function loadProducts(filter = currentFilter) {
  currentFilter = filter;
  const grid = document.getElementById('products-grid');
  const countText = document.getElementById('item-count-text');

  try {
    const res = await fetch('/api/products');
    if (!res.ok) {
      throw new Error(`Failed to fetch products (HTTP ${res.status})`);
    }
    const data = await res.json();
    PRODUCTS = data.map(p => ({
      ...p,
      stockLevel: p.stock <= 5 ? 'low-stock' : 'in-stock',
      icon: CATEGORY_ICONS[p.category] || DEFAULT_ICON
    }));
    renderProducts(currentFilter);
  } catch (err) {
    console.error('loadProducts error:', err);
    if (grid) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--radius-md);">
          <strong style="color: var(--text-main); display: block; margin-bottom: 6px;">Unable to load products</strong>
          <span>${err.message}</span>
        </div>`;
    }
    if (countText) countText.textContent = 'Products unavailable';
  }
}

function renderProducts(filter) {
  const grid = document.getElementById('products-grid');
  const countText = document.getElementById('item-count-text');
  if (!grid) return;

  const visible = filter ? PRODUCTS.filter(p => p.category === filter) : PRODUCTS;

  if (countText) {
    countText.textContent = `Showing ${visible.length} product${visible.length !== 1 ? 's' : ''}`;
  }

  if (visible.length === 0) {
    grid.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--text-muted);">
        No products found in this category.
      </div>`;
    return;
  }

  grid.innerHTML = visible.map(p => {
    const stockLabel = p.stockLevel === 'low-stock'
      ? `Low Stock (${p.stock} units)`
      : `In Stock (${p.stock} units)`;
    return `
      <article class="product-card" data-product-id="${p.id}">
        <div class="card-header">
          <span class="sku-tag">${p.sku}</span>
          <span class="category-tag">${p.category}</span>
        </div>
        <div class="product-schematic" aria-hidden="true">${p.icon}</div>
        <h2 class="product-title">${p.name}</h2>
        <p class="product-description">${p.description}</p>
        <div class="stock-indicator ${p.stockLevel}">
          <span>●</span>
          <span>${stockLabel}</span>
        </div>
        <div class="card-footer">
          <span class="product-price">${fmt(p.price)}</span>
          <button class="btn-add-cart" type="button" data-id="${p.id}" ${p.stock <= 0 ? 'disabled' : ''}>
            ${p.stock <= 0 ? 'Sold Out' : 'Add to Cart'}
          </button>
        </div>
      </article>`;
  }).join('');

  // Wire up add-to-cart buttons
  grid.querySelectorAll('.btn-add-cart').forEach(btn => {
    btn.addEventListener('click', () => addToCart(parseInt(btn.dataset.id)));
  });
}

// ---------------------------------------------------------------------------
// Render: cart sidebar
// ---------------------------------------------------------------------------
function renderCart() {
  const entries = Object.values(cart);
  const count = cartItemCount();
  const subtotal = cartTotal();
  const tax = subtotal * 0.08;
  const total = subtotal + tax;

  // Count badge in header
  const badge = document.getElementById('cart-count-badge');
  if (badge) badge.textContent = count;

  // Sidebar header count
  const cartItemCountEl = document.getElementById('cart-item-count');
  if (cartItemCountEl) {
    cartItemCountEl.textContent = count === 0 ? '0 items' : `${count} item${count !== 1 ? 's' : ''}`;
  }

  // Cart body
  const cartBody = document.getElementById('cart-body');
  const cartEmpty = document.getElementById('cart-empty-state');
  const checkoutBtn = document.getElementById('btn-checkout');

  if (entries.length === 0) {
    if (cartEmpty) cartEmpty.style.display = 'flex';
    if (cartBody) cartBody.style.display = 'none';
    if (checkoutBtn) {
      checkoutBtn.disabled = true;
      checkoutBtn.textContent = 'Cart is empty';
    }
  } else {
    if (cartEmpty) cartEmpty.style.display = 'none';
    if (cartBody) {
      cartBody.style.display = 'block';
      cartBody.innerHTML = entries.map(({ product, qty }) => `
        <div class="cart-line-item">
          <div class="cart-line-info">
            <span class="cart-line-name">${product.name}</span>
            <span class="cart-line-price">${fmt(product.price)}</span>
          </div>
          <div class="cart-line-controls">
            <button class="cart-qty-btn" data-action="dec" data-id="${product.id}">−</button>
            <span class="cart-qty-value">${qty}</span>
            <button class="cart-qty-btn" data-action="inc" data-id="${product.id}">+</button>
            <button class="cart-remove-btn" data-id="${product.id}" title="Remove">✕</button>
          </div>
        </div>
      `).join('');

      // Wire up qty controls
      cartBody.querySelectorAll('.cart-qty-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = parseInt(btn.dataset.id);
          if (btn.dataset.action === 'inc') addToCart(id);
          else decrementCart(id);
        });
      });
      cartBody.querySelectorAll('.cart-remove-btn').forEach(btn => {
        btn.addEventListener('click', () => removeFromCart(parseInt(btn.dataset.id)));
      });
    }

    if (checkoutBtn) {
      checkoutBtn.disabled = false;
      checkoutBtn.textContent = 'Place Order';
    }
  }

  // Totals
  const subtotalEl = document.getElementById('summary-subtotal');
  const taxEl = document.getElementById('summary-tax');
  const totalEl = document.getElementById('summary-total');
  if (subtotalEl) subtotalEl.textContent = fmt(subtotal);
  if (taxEl) taxEl.textContent = fmt(tax);
  if (totalEl) totalEl.textContent = fmt(total);
}

// ---------------------------------------------------------------------------
// Cart mutations
// ---------------------------------------------------------------------------
function addToCart(id) {
  const product = PRODUCTS.find(p => p.id === id);
  if (!product) return;
  if (cart[id]) {
    cart[id].qty++;
  } else {
    cart[id] = { product, qty: 1 };
  }
  renderCart();
}

function decrementCart(id) {
  if (!cart[id]) return;
  cart[id].qty--;
  if (cart[id].qty <= 0) delete cart[id];
  renderCart();
}

function removeFromCart(id) {
  delete cart[id];
  renderCart();
}

// ---------------------------------------------------------------------------
// Buy / checkout flow (Connected to /api/checkout)
// ---------------------------------------------------------------------------
async function handleCheckout() {
  const btn = document.getElementById('btn-checkout');
  if (!btn || btn.disabled) return;

  const entries = Object.values(cart);
  if (entries.length === 0) return;

  // Show processing state
  btn.disabled = true;
  btn.textContent = 'Processing…';

  try {
    // Send primary item to checkout per Section 5 {product_id, qty}
    const firstEntry = entries[0];
    const response = await fetch('/api/checkout', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        product_id: firstEntry.product.id,
        qty: firstEntry.qty
      })
    });

    if (!response.ok) {
      let detailMsg = `HTTP ${response.status}`;
      try {
        const errJson = await response.json();
        detailMsg = errJson.detail || detailMsg;
      } catch (_) {}
      throw new Error(`Checkout failed: ${detailMsg}`);
    }

    const orderData = await response.json();
    const orderId = orderData.order_id || 'ORD-CONFIRMED';
    const count = cartItemCount();

    // Clear the cart
    Object.keys(cart).forEach(k => delete cart[k]);
    renderCart();

    // Show confirmation banner
    showOrderConfirmation(orderId, count);

    // Refresh products to reflect updated inventory in DB
    loadProducts();

  } catch (err) {
    console.error('Checkout failed:', err);
    showOrderError(err.message || 'Checkout failed');
    btn.disabled = false;
    btn.textContent = 'Place Order';
  }
}

function showOrderConfirmation(orderId, itemCount) {
  const oldError = document.getElementById('order-error');
  if (oldError) oldError.remove();

  let banner = document.getElementById('order-confirmation');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'order-confirmation';
    banner.className = 'order-confirmation';
    document.querySelector('.app-main').prepend(banner);
  }
  banner.innerHTML = `
    <div class="order-confirmation-inner">
      <span class="order-confirmation-icon">✓</span>
      <div>
        <strong>Order placed successfully</strong>
        <span>${orderId} — ${itemCount} item${itemCount !== 1 ? 's' : ''} confirmed in database</span>
      </div>
      <button class="order-dismiss-btn" type="button" onclick="this.closest('.order-confirmation').remove()">✕</button>
    </div>`;
}

function showOrderError(message) {
  const oldConf = document.getElementById('order-confirmation');
  if (oldConf) oldConf.remove();

  let banner = document.getElementById('order-error');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'order-error';
    banner.className = 'order-error';
    document.querySelector('.app-main').prepend(banner);
  }
  banner.innerHTML = `
    <div class="order-confirmation-inner">
      <span class="order-error-icon">✕</span>
      <div>
        <strong>Checkout Error</strong>
        <span>${message}</span>
      </div>
      <button class="order-dismiss-btn" type="button" onclick="this.closest('.order-error').remove()">✕</button>
    </div>`;
}

// ---------------------------------------------------------------------------
// Filter toolbar
// ---------------------------------------------------------------------------
function initFilters() {
  const toolbar = document.getElementById('filter-group');
  if (!toolbar) return;

  toolbar.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      toolbar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.dataset.filter || null;
      loadProducts(cat);
    });
  });
}

// ---------------------------------------------------------------------------
// Fault panel (UI toggle buttons)
// ---------------------------------------------------------------------------
const FAULTS = [
  { id: 'db_latency',         label: 'db › Add Latency',       service: 'db',       desc: 'Inject 800ms latency on db queries.' },
  { id: 'db_errors',          label: 'db › Return Errors',      service: 'db',       desc: 'db returns 500 at 60% rate.' },
  { id: 'db_pool_exhausted',  label: 'db › Exhaust Pool',       service: 'db',       desc: 'Hold all pool slots for 60s.' },
  { id: 'checkout_crash',     label: 'checkout › Crash',        service: 'checkout', desc: 'Stop the checkout container.' },
  { id: 'checkout_memory_leak', label: 'checkout › Memory Leak', service: 'checkout', desc: 'Allocate 1MB/request until OOM.' },
  { id: 'bad_deploy',         label: 'checkout › Bad Deploy',   service: 'checkout', desc: 'Set payment_timeout_ms=50 + deploy event.' },
];

function renderFaultPanel() {
  const list = document.getElementById('fault-list');
  if (!list) return;

  list.innerHTML = FAULTS.map(f => `
    <div class="fault-item">
      <div class="fault-meta">
        <span class="fault-label">${f.label}</span>
        <span class="fault-desc">${f.desc}</span>
      </div>
      <button class="fault-trigger-btn" type="button" data-fault="${f.id}">Inject</button>
    </div>
  `).join('');

  list.querySelectorAll('.fault-trigger-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const fault = FAULTS.find(f => f.id === btn.dataset.fault);
      if (!fault) return;
      setFaultStatus(fault.id, 'injecting', `Injecting ${fault.id}…`);
      setTimeout(() => {
        setFaultStatus(fault.id, 'active', `${fault.id} active (mock — real injection in Stage 4)`);
        btn.textContent = 'Active';
        btn.classList.add('fault-active');
      }, 400);
    });
  });

  const resetBtn = document.getElementById('fault-reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      list.querySelectorAll('.fault-trigger-btn').forEach(btn => {
        btn.textContent = 'Inject';
        btn.classList.remove('fault-active');
      });
      setFaultStatus('reset', 'idle', 'All faults reset. System nominal.');
    });
  }
}

function setFaultStatus(faultId, state, message) {
  const statusEl = document.getElementById('fault-status-text');
  if (statusEl) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }
}

// ---------------------------------------------------------------------------
// Theme toggle
// ---------------------------------------------------------------------------
function initThemeToggle() {
  const btn = document.getElementById('theme-toggle');
  const text = document.getElementById('theme-toggle-text');

  function syncLabel() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (text) text.textContent = isDark ? 'Light' : 'Dark';
  }
  syncLabel();

  btn?.addEventListener('click', () => {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('shoplite_theme', next);
    syncLabel();
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  loadProducts(null);
  renderCart();
  initFilters();
  renderFaultPanel();
  initThemeToggle();

  const checkoutBtn = document.getElementById('btn-checkout');
  if (checkoutBtn) {
    checkoutBtn.addEventListener('click', handleCheckout);
  }
});
