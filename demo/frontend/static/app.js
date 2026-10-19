/**
 * ShopLite Stage 2: In-memory cart, buy flow, fault panel.
 * No fetch(), no network calls. All data from JS array.
 */

// ---------------------------------------------------------------------------
// Product data (mock — will be replaced by real API in Stage 3)
// ---------------------------------------------------------------------------
const PRODUCTS = [
  {
    id: 1,
    sku: 'SKU-8821',
    category: 'Keyboards',
    name: 'Keychron Q1 Pro Mechanical Keyboard',
    description: '75% layout custom mechanical keyboard, fully CNC machined aluminum body, hot-swappable switches, double-gasket dampening.',
    price: 199.00,
    stock: 14,
    stockLevel: 'in-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
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
    </svg>`
  },
  {
    id: 2,
    sku: 'SKU-4412',
    category: 'Peripherals',
    name: 'Logitech MX Master 3S Mouse',
    description: '8,000 DPI Darkfield sensor tracks on glass. Quiet clicks, MagSpeed electromagnetic scroll wheel, USB-C fast recharging.',
    price: 99.00,
    stock: 28,
    stockLevel: 'in-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
      <rect x="5" y="2" width="14" height="20" rx="4"></rect>
      <line x1="12" y1="6" x2="12" y2="10"></line>
    </svg>`
  },
  {
    id: 3,
    sku: 'SKU-9905',
    category: 'Displays',
    name: 'Dell UltraSharp 27" 4K Monitor',
    description: 'U2723QE IPS Black panel with 2000:1 contrast ratio. 98% DCI-P3 color gamut, 90W USB-C hub connectivity with RJ45 Ethernet.',
    price: 489.00,
    stock: 6,
    stockLevel: 'in-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
      <rect x="2" y="3" width="20" height="14" rx="1"></rect>
      <line x1="8" y1="21" x2="16" y2="21"></line>
      <line x1="12" y1="17" x2="12" y2="21"></line>
    </svg>`
  },
  {
    id: 4,
    sku: 'SKU-2319',
    category: 'Audio',
    name: 'Sony WH-1000XM5 Headset',
    description: 'Active noise cancellation powered by dual V1/QN1 processors. 8 beamforming mics with AI noise reduction for crisp voice calls.',
    price: 279.00,
    stock: 19,
    stockLevel: 'in-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
      <path d="M3 18v-6a9 9 0 0 1 18 0v6"></path>
      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"></path>
    </svg>`
  },
  {
    id: 5,
    sku: 'SKU-6120',
    category: 'Hardware',
    name: 'CalDigit TS4 Thunderbolt 4 Dock',
    description: '18 input/output ports with 98W host charging, 2.5 Gigabit Ethernet, dual 4K/60Hz monitor support, and front UHS-II SD reader.',
    price: 379.00,
    stock: 3,
    stockLevel: 'low-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
      <rect x="2" y="7" width="20" height="10" rx="1"></rect>
      <line x1="6" y1="12" x2="8" y2="12"></line>
      <line x1="11" y1="12" x2="13" y2="12"></line>
      <line x1="16" y1="12" x2="18" y2="12"></line>
    </svg>`
  },
  {
    id: 6,
    sku: 'SKU-1084',
    category: 'Accessories',
    name: 'Heavy-Duty Gas Spring Monitor Arm',
    description: 'Supports ultrawide displays up to 34 inches (19.8 lbs). Quick-release VESA 75/100 plate, integrated cable management channel.',
    price: 74.00,
    stock: 35,
    stockLevel: 'in-stock',
    icon: `<svg class="schematic-svg" viewBox="0 0 24 24">
      <path d="M12 2v8"></path>
      <path d="M4 10h16"></path>
      <rect x="8" y="14" width="8" height="6" rx="1"></rect>
      <line x1="12" y1="10" x2="12" y2="14"></line>
    </svg>`
  }
];

// ---------------------------------------------------------------------------
// Cart state
// ---------------------------------------------------------------------------
// cart = { [productId]: { product, qty } }
const cart = {};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmt(n) {
  return '$' + n.toFixed(2);
}

function cartTotal() {
  return Object.values(cart).reduce((sum, { product, qty }) => sum + product.price * qty, 0);
}

function cartItemCount() {
  return Object.values(cart).reduce((sum, { qty }) => sum + qty, 0);
}

// ---------------------------------------------------------------------------
// Render: product grid
// ---------------------------------------------------------------------------
function renderProducts(filter) {
  const grid = document.getElementById('products-grid');
  const countText = document.getElementById('item-count-text');

  const visible = filter ? PRODUCTS.filter(p => p.category === filter) : PRODUCTS;

  countText.textContent = `Showing ${visible.length} product${visible.length !== 1 ? 's' : ''}`;

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
          <button class="btn-add-cart" type="button" data-id="${p.id}">Add to Cart</button>
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
  document.getElementById('cart-count-badge').textContent = count;

  // Sidebar header count
  document.getElementById('cart-item-count').textContent =
    count === 0 ? '0 items' : `${count} item${count !== 1 ? 's' : ''}`;

  // Cart body
  const cartBody = document.getElementById('cart-body');
  const cartEmpty = document.getElementById('cart-empty-state');
  const checkoutBtn = document.getElementById('btn-checkout');

  if (entries.length === 0) {
    cartEmpty.style.display = 'flex';
    cartBody.style.display = 'none';
    checkoutBtn.disabled = true;
    checkoutBtn.textContent = 'Cart is empty';
  } else {
    cartEmpty.style.display = 'none';
    cartBody.style.display = 'block';
    checkoutBtn.disabled = false;
    checkoutBtn.textContent = 'Place Order';

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

  // Totals
  document.getElementById('summary-subtotal').textContent = fmt(subtotal);
  document.getElementById('summary-tax').textContent = fmt(tax);
  document.getElementById('summary-total').textContent = fmt(total);
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
// Buy / checkout flow (fake — no network)
// ---------------------------------------------------------------------------
function handleCheckout() {
  const btn = document.getElementById('btn-checkout');
  if (btn.disabled) return;

  // Show processing state
  btn.disabled = true;
  btn.textContent = 'Processing…';

  setTimeout(() => {
    // Fake order ID
    const orderId = 'ORD-' + Math.floor(Math.random() * 900000 + 100000);
    const count = cartItemCount();

    // Clear the cart
    Object.keys(cart).forEach(k => delete cart[k]);
    renderCart();

    // Show confirmation banner
    showOrderConfirmation(orderId, count);
  }, 900);
}

function showOrderConfirmation(orderId, itemCount) {
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
        <span>${orderId} — ${itemCount} item${itemCount !== 1 ? 's' : ''} confirmed (mock, Stage 2)</span>
      </div>
      <button class="order-dismiss-btn" type="button" onclick="this.closest('.order-confirmation').remove()">✕</button>
    </div>`;
}

// ---------------------------------------------------------------------------
// Filter toolbar
// ---------------------------------------------------------------------------
function initFilters() {
  const categories = ['Keyboards', 'Displays', 'Accessories'];
  const toolbar = document.getElementById('filter-group');

  toolbar.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      toolbar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.dataset.filter || null;
      renderProducts(cat);
    });
  });
}

// ---------------------------------------------------------------------------
// Fault panel (buttons only update status text — no network)
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

  document.getElementById('fault-reset-btn').addEventListener('click', () => {
    list.querySelectorAll('.fault-trigger-btn').forEach(btn => {
      btn.textContent = 'Inject';
      btn.classList.remove('fault-active');
    });
    setFaultStatus('reset', 'idle', 'All faults reset. System nominal.');
  });
}

function setFaultStatus(faultId, state, message) {
  const statusEl = document.getElementById('fault-status-text');
  statusEl.dataset.state = state;
  statusEl.textContent = message;
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
  renderProducts(null);
  renderCart();
  initFilters();
  renderFaultPanel();
  initThemeToggle();

  document.getElementById('btn-checkout').addEventListener('click', handleCheckout);
});
