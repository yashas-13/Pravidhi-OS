/**
 * Firebase end-user authentication for the static Pravidhi Commander dashboard.
 *
 * Firebase identity is intentionally NOT treated as authorization for protected
 * Pravidhi APIs. The existing Keycloak sign-in remains required for dashboard
 * API access until a server-side Firebase ID-token exchange/validation flow is
 * implemented and tested.
 */
import { initializeApp, getApps } from "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithPopup,
  sendPasswordResetEmail,
  signOut,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyBQVTcLn6TUOmBHuFlCe2wZMbmSFecJBQA",
  authDomain: "pravidhi-os.firebaseapp.com",
  projectId: "pravidhi-os",
  storageBucket: "pravidhi-os.firebasestorage.app",
  messagingSenderId: "314825143687",
  appId: "1:314825143687:web:1963c7fa4ce4c276eccf22",
  measurementId: "G-SVY3V6HDZ6",
};

const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
provider.setCustomParameters({ prompt: "select_account" });

const css = `
.firebase-auth { margin-top: 18px; padding-top: 18px; border-top: 1px solid #30343b; text-align: left; }
.firebase-auth h2 { font-size: 16px; margin: 0 0 6px; }
.firebase-auth p { color: #a7adb7; font-size: 13px; line-height: 1.5; }
.firebase-auth label { display:block; font-size:12px; margin:10px 0 5px; color:#c6cbd3; }
.firebase-auth input { width:100%; box-sizing:border-box; padding:11px; border:1px solid #3b414b; border-radius:8px; background:#11151b; color:#f4f6f8; }
.firebase-auth button { margin-top:10px; width:100%; cursor:pointer; }
.firebase-auth .firebase-secondary { background:#20252d; color:#f4f6f8; border:1px solid #3b414b; border-radius:8px; padding:10px; }
.firebase-auth .firebase-message { overflow-wrap:anywhere; margin-top:10px; font-size:12px; }
.firebase-auth .firebase-message.error { color:#ff9b9b; }
.firebase-auth .firebase-message.ok { color:#9de2b0; }
.firebase-auth .firebase-actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
`;

function addStyles() {
  if (document.querySelector("#firebase-auth-styles")) return;
  const style = document.createElement("style");
  style.id = "firebase-auth-styles";
  style.textContent = css;
  document.head.appendChild(style);
}

function message(el, text, kind = "ok") {
  el.textContent = text;
  el.className = "firebase-message " + kind;
}

function friendlyError(error) {
  const map = {
    "auth/email-already-in-use": "An account already exists for this email.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/weak-password": "Choose a stronger password (at least 6 characters).",
    "auth/invalid-credential": "Email or password is incorrect.",
    "auth/popup-closed-by-user": "Google sign-in was cancelled.",
    "auth/popup-blocked": "Your browser blocked the sign-in popup. Allow popups and retry.",
    "auth/too-many-requests": "Too many attempts. Wait a while and try again.",
    "auth/unauthorized-domain": "This domain is not authorized in Firebase Authentication settings.",
    "auth/network-request-failed": "Network error. Check your connection and retry.",
  };
  return map[error?.code] || "Authentication failed. Please retry.";
}

function mount() {
  const card = document.querySelector("#app .login.card");
  if (!card || card.querySelector(".firebase-auth")) return;
  addStyles();

  const section = document.createElement("section");
  section.className = "firebase-auth";
  section.innerHTML = `
    <h2>Pravidhi OS account</h2>
    <p>Register or sign in with Firebase. Protected dashboard operations still require the existing Pravidhi identity sign-in.</p>
    <div class="firebase-form">
      <label for="firebase-email">Email</label>
      <input id="firebase-email" type="email" autocomplete="email" required placeholder="you@example.com">
      <label for="firebase-password">Password</label>
      <input id="firebase-password" type="password" autocomplete="current-password" minlength="6" placeholder="At least 6 characters">
      <div class="firebase-actions">
        <button class="firebase-secondary" id="firebase-register" type="button">Create account</button>
        <button class="firebase-secondary" id="firebase-login" type="button">Sign in</button>
      </div>
      <button class="firebase-secondary" id="firebase-google" type="button>">Continue with Google</button>
      <button class="firebase-secondary" id="firebase-reset" type="button">Send password reset email</button>
      <button class="firebase-secondary" id="firebase-logout" type="button" hidden>Sign out of Firebase</button>
      <div id="firebase-message" class="firebase-message" role="status" aria-live="polite"></div>
    </div>`;
  // Correct the attribute defensively before inserting into the DOM.
  section.querySelector("#firebase-google").type = "button";
  card.appendChild(section);

  const email = section.querySelector("#firebase-email");
  const password = section.querySelector("#firebase-password");
  const status = section.querySelector("#firebase-message");
  const googleButton = section.querySelector("#firebase-google");
  const registerButton = section.querySelector("#firebase-register");
  const loginButton = section.querySelector("#firebase-login");
  const resetButton = section.querySelector("#firebase-reset");
  const logoutButton = section.querySelector("#firebase-logout");

  const run = async (fn) => {
    [registerButton, loginButton, googleButton, resetButton, logoutButton].forEach(b => b.disabled = true);
    try { await fn(); }
    catch (error) { message(status, friendlyError(error), "error"); }
    finally { [registerButton, loginButton, googleButton, resetButton, logoutButton].forEach(b => b.disabled = false); }
  };

  registerButton.addEventListener("click", () => run(async () => {
    if (!email.value.trim() || password.value.length < 6) {
      message(status, "Enter an email and a password of at least 6 characters.", "error");
      return;
    }
    const result = await createUserWithEmailAndPassword(auth, email.value.trim(), password.value);
    message(status, `Firebase account created for ${result.user.email}. Use “Sign in with Pravidh” above for protected dashboard access.`);
  }));

  loginButton.addEventListener("click", () => run(async () => {
    if (!email.value.trim() || !password.value) {
      message(status, "Enter your email and password.", "error");
      return;
    }
    const result = await signInWithEmailAndPassword(auth, email.value.trim(), password.value);
    message(status, `Signed in to Firebase as ${result.user.email}. Protected dashboard access still requires Keycloak.`);
  }));

  googleButton.addEventListener("click", () => run(async () => {
    const result = await signInWithPopup(auth, provider);
    message(status, `Google sign-in succeeded for ${result.user.email || result.user.uid}. Protected dashboard access still requires Keycloak.`);
  }));

  resetButton.addEventListener("click", () => run(async () => {
    if (!email.value.trim()) {
      message(status, "Enter your email address first.", "error");
      return;
    }
    await sendPasswordResetEmail(auth, email.value.trim());
    message(status, "If the account exists, Firebase has sent a password-reset email.");
  }));

  logoutButton.addEventListener("click", () => run(async () => {
    await signOut(auth);
    message(status, "Signed out of Firebase.");
  }));

  onAuthStateChanged(auth, user => {
    logoutButton.hidden = !user;
    if (user) message(status, `Firebase session active: ${user.email || user.uid}. Keycloak remains required for protected APIs.`);
  });
}

// The legacy dashboard renders its login view dynamically after page load.
const observer = new MutationObserver(mount);
observer.observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
mount();
