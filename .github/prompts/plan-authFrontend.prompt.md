# Plan: Frontend Authentication with Login/Register Pages

Implement a complete authentication flow with beautiful shadcn/ui pages for student and teacher login/registration, including JWT token management and role-based home page.

## Steps

1. **Install dependencies**: Install `react-router-dom`, `react-hook-form`, `zod`, and `@hookform/resolvers` for routing and form validation and axios for requests. 

2. **Install shadcn/ui components**: Use mcp tools to list the components and think of best ways to make a beautiful UI ouf these components.

3. **Create auth context & token service**: Add [frontend/src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx) with React Context to manage user state, JWT token (localStorage), and expose `login`, `register`, `logout` functions. Create [frontend/src/services/api.ts](frontend/src/services/api.ts) as a fetch wrapper that auto-injects the Bearer token.

4. **Create Login page**: Build [frontend/src/pages/Login.tsx](frontend/src/pages/Login.tsx) with email/password form using shadcn `Card`, `Input`, `Label`, `Button`, `Form` components. Call `POST /auth/login` and store returned token.

5. **Create Register page**: Build [frontend/src/pages/Register.tsx](frontend/src/pages/Register.tsx) with first_name, last_name, email, password, and role (`Select` for student/teacher). Call `POST /auth/register`, redirect to login on success.

6. **Create Home page with role-based greeting**: Build [frontend/src/pages/Home.tsx](frontend/src/pages/Home.tsx) displaying "Welcome, [name]!" with different UI/messaging for students vs teachers based on decoded JWT role.

7. **Set up routing**: Update [frontend/src/App.tsx](frontend/src/App.tsx) with `react-router-dom` routes (`/login`, `/register`, `/home`), wrap app in `AuthProvider`, add protected route logic redirecting unauthenticated users to login.

## Further Considerations

1. **Token storage strategy**: Use localStorage (persists across tabs/sessions) or sessionStorage (clears on tab close)? Recommend **localStorage** with token expiry check.

2. **Backend URL configuration**: Should we use environment variables (`VITE_API_URL`) for the backend URL (currently likely `http://localhost:8000`)? Recommend **yes** for flexibility.

3. **Separate branch workflow**: Create branch `feature/auth-frontend`, implement changes, then merge to `main` via PR — confirm this approach is acceptable?

## Backend API Reference

### POST /auth/register - User Registration
**Request Body:**
```json
{
  "first_name": "string (1-100 chars, required)",
  "last_name": "string (1-100 chars, required)",
  "email": "string (valid email, required)",
  "password": "string (min 8 chars, required)",
  "role": "student" | "teacher"
}
```

**Response (201 Created):**
```json
{
  "id": "integer",
  "first_name": "string",
  "last_name": "string",
  "email": "string",
  "role": "student" | "teacher",
  "created_at": "datetime"
}
```

**Errors:**
- `400 Bad Request`: "Email already registered"

### POST /auth/login - User Login
**Request Body:**
```json
{
  "email": "string (valid email)",
  "password": "string"
}
```

**Response (200 OK):**
```json
{
  "access_token": "string (JWT)",
  "token_type": "bearer"
}
```

**Errors:**
- `401 Unauthorized`: "Incorrect email or password"

### JWT Token Details
- Algorithm: `HS256`
- Expiration: 60 minutes
- Payload includes: `sub` (email), `role` (user role), `exp` (expiration)

## Tech Stack
- React 
- Vite 
- TypeScript
- Tailwind CSS
- shadcn/ui 
- lucide-react for icons
