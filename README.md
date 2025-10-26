Implementation Steps
1. Backend Setup
bash# File structure
src/
├── models/
│   ├── products.py         # Product, Cart, Order models
│   └── userModel.py        # Existing User model
├── schemas/
│   ├── productSchemas.py   # Pydantic schemas
│   └── userSchema.py       # Existing user schemas
├── services/
│   ├── cartService.py      # Cart business logic
│   └── productService.py   # Product business logic
├── crud/
│   ├── userCrud.py         # Existing auth setup
│   └── productCrud.py      # Product CRUD (optional if using services)
└── routes/
    ├── users.py            # Existing user routes
    └── products.py         # New product/cart routes

2. Frontend Setup
bash# File structure
src/
├── stores/
│   ├── products.ts         # Product store (Vuex pattern)
│   └── cart.ts             # Cart store (Vuex pattern)
├── composables/
│   ├── useApi.ts           # API integration layer
│   └── usePersistCart.ts   # REMOVED - persistence now server-side
├── components/
│   ├── ProductCard.vue     # Updated to work with new store
│   ├── CartCard.vue        # Updated to use new cart store
│   └── Nav.vue             # Already compatible
└── views/
    ├── Home.vue            # List products
    ├── Cart.vue            # Cart page
    └── Product.vue         # Product detail
3. Environment Variables
env# Frontend (.env)
VITE_API_URL=http://localhost:8000/api

# Backend (.env)
JWT_SECRET_KEY=your_secret_key
MONGODB_URL=mongodb://localhost:27017/your_db
FRONTEND_URL=http://localhost:5173