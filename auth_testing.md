# Smart Health ID Authentication Testing

Demo users are seeded on startup. Use `Demo@123` with:
- patient@example.com
- doctor@example.com
- hospital@example.com

Verify POST `/api/auth/login`, GET `/api/auth/me` with the returned bearer token, and POST `/api/auth/logout`.