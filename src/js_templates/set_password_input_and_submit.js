// 機能: password入力欄に値を設定し、フォームを送信またはボタンをクリックします。
// 呼び出し元: set_password_input_and_submit 関数 (arim_rde_tool.py)

(function(){
    var input = document.getElementById('password');
    if(input) {
        input.value = '{value}';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        var form = document.getElementById('login');
        if(form) {form.submit();return 'set_and_submitted';}
        var btn = Array.from(document.querySelectorAll('button.btn.btn-info[type=submit]')).find(function(b){return b.innerText.includes('Next');})
        || document.querySelector('button[type=submit]');
        if(btn && !btn.disabled) {btn.click();return 'set_and_clicked';}
        return 'set_only';
    }
    return 'no_input';
})();
