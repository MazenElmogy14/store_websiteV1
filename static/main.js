document.addEventListener("DOMContentLoaded", () => {
    updateCartBadge();
    updateWishlistBadge();
    initWishlistButtons();
    if (window.location.pathname.includes("/cart")) renderCartPage();

    // --- تفعيل تأثير ظهور العناصر عند التمرير (Scroll-Reveal Observer) ---
    const revealOptions = {
        threshold: 0.05,
        rootMargin: "0px 0px -40px 0px"
    };

    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach((entry, idx) => {
            if (entry.isIntersecting) {
                setTimeout(() => {
                    entry.target.style.animation = "fadeInUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards";
                    entry.target.style.opacity = "1";
                }, idx * 60); // تأثير متتابع أنيق للمنتجات المتجاورة
                observer.unobserve(entry.target);
            }
        });
    }, revealOptions);

    const elementsToReveal = document.querySelectorAll('.product-card, .search-sort-bar, .category-filter-bar, footer');
    elementsToReveal.forEach(el => {
        el.style.opacity = "0";
        revealObserver.observe(el);
    });
});

/* ==========================================================================
   إشعارات التوست الراقية (Toast Alerts Manager)
   ========================================================================== */
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    let icon = '<i class="fa-solid fa-circle-check"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-circle-exclamation"></i>';
    if (type === 'heart') icon = '<i class="fa-solid fa-heart" style="color:#e74c3c;"></i>';
    
    toast.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 100);
    setTimeout(() => { 
        toast.classList.remove('show'); 
        setTimeout(() => toast.remove(), 400); 
    }, 3000);
}

/* ==========================================================================
   إدارة عربة التسوق والمشتريات (Shopping Cart Engine)
   ========================================================================== */
function getCart() { return JSON.parse(localStorage.getItem("salla")) || []; }
function saveCart(cart) { localStorage.setItem("salla", JSON.stringify(cart)); updateCartBadge(); }
function updateCartBadge() { const badge = document.getElementById("cart-count"); if (badge) badge.innerText = getCart().reduce((sum, item) => sum + item.quantity, 0); }

function addToCart(id, name, price) {
    let cart = getCart();
    const existing = cart.find(item => item.id === id);
    if (existing) existing.quantity += 1;
    else cart.push({ id, name, price, quantity: 1 });
    saveCart(cart);
    showToast(`تمت إضافة "${name}" إلى السلة! 🛒`, 'success');
    closeQuickViewModal();
}

function renderCartPage() {
    const cart = getCart();
    const tbody = document.getElementById("cart-items-body");
    const emptyState = document.getElementById("cart-empty");
    const contentState = document.getElementById("cart-content");
    const totalSpan = document.getElementById("total-price");
    if (!tbody) return;

    if (cart.length === 0) {
        if(emptyState) emptyState.style.display = "block";
        if(contentState) contentState.style.display = "none";
        return;
    }
    if(emptyState) emptyState.style.display = "none";
    if(contentState) contentState.style.display = "grid";
    tbody.innerHTML = "";
    
    let total = 0;
    cart.forEach((item, index) => {
        const itemTotal = item.price * item.quantity;
        total += itemTotal;
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><strong>${item.name}</strong></td>
            <td>${item.price} ج.م</td>
            <td>
                <button onclick="changeQty(${index}, -1)">-</button><span style="margin: 0 8px;">${item.quantity}</span><button onclick="changeQty(${index}, 1)">+</button>
            </td>
            <td>${itemTotal} ج.م</td>
            <td><button onclick="removeItem(${index})" style="color: red; border: none; background: none; cursor: pointer;"><i class="fa-solid fa-trash"></i></button></td>
        `;
        tbody.appendChild(tr);
    });
    if(totalSpan) totalSpan.innerText = total;
    
    const hiddenCoupon = document.getElementById("applied_coupon_input");
    if (hiddenCoupon && hiddenCoupon.value) { document.getElementById("coupon_input").value = hiddenCoupon.value; applyCoupon(); }
}

function changeQty(index, delta) { let cart = getCart(); cart[index].quantity += delta; if (cart[index].quantity <= 0) cart.splice(index, 1); saveCart(cart); renderCartPage(); }
function removeItem(index) { let cart = getCart(); cart.splice(index, 1); saveCart(cart); renderCartPage(); showToast("تم حذف المنتج من السلة", "error"); }
function prepareCartData() { const hiddenInput = document.getElementById("cart_data_input"); if (hiddenInput) hiddenInput.value = JSON.stringify(getCart()); return true; }

/* ==========================================================================
   أكواد الخصم والبحث والمودال (Coupons, Live Search & Modals)
   ========================================================================== */
function applyCoupon() {
    const code = document.getElementById("coupon_input").value.trim();
    const total = parseFloat(document.getElementById("total-price").innerText);
    const msgSpan = document.getElementById("coupon-msg");
    const discBox = document.getElementById("discount-display-box");
    const hiddenCoupon = document.getElementById("applied_coupon_input");
    
    if (!code) { msgSpan.style.color = "red"; msgSpan.innerText = "اكتب الكود أولاً"; return; }
    
    fetch("/api/validate_coupon", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: code, total: total, cart: getCart() })
    }).then(res => res.json()).then(data => {
        if (data.valid) {
            msgSpan.style.color = "#27ae60"; msgSpan.innerText = data.message;
            discBox.style.display = "block";
            document.getElementById("discount-val").innerText = data.discount_amount;
            document.getElementById("final-total-val").innerText = data.new_total;
            if(hiddenCoupon) hiddenCoupon.value = code;
            showToast("تم تطبيق الكوبون بنجاح 🎉", "success");
        } else {
            msgSpan.style.color = "#e74c3c"; msgSpan.innerText = data.message;
            discBox.style.display = "none";
            if(hiddenCoupon) hiddenCoupon.value = "";
            showToast(data.message, "error");
        }
    });
}

function filterProducts() {
    const query = document.getElementById("live-search-input").value.toLowerCase().trim();
    const cards = document.querySelectorAll(".product-card");
    let visibleCount = 0;
    cards.forEach(card => {
        if (card.getAttribute("data-name").toLowerCase().includes(query) || card.getAttribute("data-desc").toLowerCase().includes(query)) {
            card.style.display = "flex"; visibleCount++;
        } else card.style.display = "none";
    });
    document.getElementById("no-search-results").style.display = (visibleCount === 0 && cards.length > 0) ? "block" : "none";
}

function sortProducts() {
    const select = document.getElementById("sort-select");
    const container = document.getElementById("products-grid-container");
    if(!select || !container) return;
    const sortType = select.value;
    const cards = Array.from(container.getElementsByClassName("product-card"));
    
    cards.sort((a, b) => {
        const priceA = parseFloat(a.getAttribute("data-price"));
        const priceB = parseFloat(b.getAttribute("data-price"));
        if (sortType === "price-low") return priceA - priceB;
        if (sortType === "price-high") return priceB - priceA;
        return parseInt(b.getAttribute("data-id")) - parseInt(a.getAttribute("data-id"));
    });
    cards.forEach(card => container.appendChild(card));
}

/* ==========================================================================
   إدارة القائمة المفضلة ونافذة المعاينة (Wishlist & Modals Animations)
   ========================================================================== */
function getWishlist() { return JSON.parse(localStorage.getItem("wishlist")) || []; }
function saveWishlist(list) { localStorage.setItem("wishlist", JSON.stringify(list)); updateWishlistBadge(); }
function updateWishlistBadge() { const badge = document.getElementById("wishlist-count"); if (badge) badge.innerText = getWishlist().length; }

function initWishlistButtons() {
    const list = getWishlist();
    document.querySelectorAll(".wishlist-card-btn").forEach(btn => {
        const id = parseInt(btn.getAttribute("data-id"));
        if (list.includes(id)) btn.classList.add("active");
        else btn.classList.remove("active");
    });
}

function toggleWishlist(id, name) {
    let list = getWishlist();
    const idx = list.indexOf(id);
    if (idx > -1) {
        list.splice(idx, 1);
        showToast(`تم حذف "${name}" من المفضلة`, 'error');
    } else {
        list.push(id);
        showToast(`تمت إضافة "${name}" إلى المفضلة ❤️`, 'heart');
    }
    saveWishlist(list);
    initWishlistButtons();
}

function openQuickView(id, name, price, desc, image) {
    const modal = document.getElementById("quickview-modal");
    if (!modal) return;
    document.getElementById("qv-name").innerText = name;
    document.getElementById("qv-desc").innerText = desc;
    document.getElementById("qv-price").innerText = price + " ج.م";
    document.getElementById("qv-img").src = image;
    document.getElementById("qv-btn").setAttribute("onclick", `addToCart(${id}, '${name}', ${price})`);
    
    modal.classList.add("show-modal");
}

function closeQuickViewModal() {
    const modal = document.getElementById("quickview-modal");
    if (modal) modal.classList.remove("show-modal");
}