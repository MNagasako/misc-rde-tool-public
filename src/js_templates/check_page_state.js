// デバッグ: ページの状態を確認
(function() {
    var result = {
        url: window.location.href,
        title: document.title,
        passwordInput: null,
        loginForm: null,
        submitButton: null,
        body_length: document.body ? document.body.innerHTML.length : 0
    };
    
    var input = document.getElementById('password');
    if (input) {
        result.passwordInput = {
            exists: true,
            value_length: input.value.length,
            type: input.type,
            disabled: input.disabled
        };
    }
    
    var form = document.getElementById('login');
    if (form) {
        result.loginForm = {
            exists: true,
            action: form.action,
            method: form.method
        };
    }
    
    var btn = document.querySelector('button[type=submit]');
    if (btn) {
        result.submitButton = {
            exists: true,
            disabled: btn.disabled,
            text: btn.innerText
        };
    }
    
    return result;
})();
