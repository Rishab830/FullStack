// Password strength logic
const passwordInput = document.getElementById('signupPassword');
const strengthBar = document.getElementById('strength-bar');

passwordInput.addEventListener('input', function () {
    const val = passwordInput.value;
    let strength = 0;
    if (val.length >= 8) strength++;
    if (/[A-Z]/.test(val)) strength++;
    if (/[a-z]/.test(val)) strength++;
    if (/\d/.test(val)) strength++;
    if (/[^a-zA-Z0-9]/.test(val)) strength++;
    let barColor = '#393939';
    if (strength <= 1) barColor = '#ff453b';
    else if (strength === 2) barColor = '#ff8c1a';
    else if (strength === 3) barColor = '#fbbf24';
    else if (strength >= 4) barColor = '#27ef54';
    strengthBar.style.background = barColor;
});

// Sign Up logic
const signupForm = document.getElementById('signupForm');
const signupError = document.getElementById('signupError');
signupForm.addEventListener('submit', function(e) {
    e.preventDefault();
    signupError.textContent = '';
    const username = document.getElementById('signupUsername').value.trim();
    const password = passwordInput.value;
    if (!username) {
    signupError.textContent = "Username is required!";
    return;
    }
    if (!password) {
    signupError.textContent = "Password is required!";
    return;
    }
    if (password.length < 6) {
    signupError.textContent = "Password must be at least 6 characters.";
    return;
    }

    // Save user in localStorage (simple, for demo purposes)
    let users = {};
    try {
    users = JSON.parse(localStorage.getItem('users')) || {};
    } catch {}
    if (users[username]) {
    signupError.textContent = "Username already exists.";
    return;
    }
    users[username] = password;  // For real apps, NEVER store plain passwords!
    localStorage.setItem('users', JSON.stringify(users));
    // Optionally set "logged in" state
    localStorage.setItem('currentUser', username);
    window.location.href = "todo.html";
});