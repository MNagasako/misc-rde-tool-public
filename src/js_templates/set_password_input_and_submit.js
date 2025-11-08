// 機能: password入力欄に値を設定し、フォームを送信またはボタンをクリックします。
// 呼び出し元: set_password_input_and_submit 関数 (arim_rde_tool.py)
// v1.20.3: PySide6対応 - より堅牢なフォーム送信方法

(function(){
    var input = document.getElementById('password');
    if(input) {
        input.value = '{value}';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        
        // ボタンクリックを優先（より確実）
        var btn = Array.from(document.querySelectorAll('button.btn.btn-info[type=submit]')).find(function(b){return b.innerText.includes('Next');})
        || document.querySelector('button[type=submit]');
        
        if(btn && !btn.disabled) {
            // PySide6対応: 少し遅延してクリック
            setTimeout(function() {
                btn.click();
            }, 100);
            return 'set_and_clicked';
        }
        
        // ボタンがない場合はフォームsubmit
        var form = document.getElementById('login');
        if(form) {
            // PySide6対応: requestSubmit()を使用（より標準的）
            if (form.requestSubmit) {
                setTimeout(function() {
                    form.requestSubmit();
                }, 100);
            } else {
                setTimeout(function() {
                    form.submit();
                }, 100);
            }
            return 'set_and_submitted';
        }
        
        return 'set_only';
    }
    return 'no_input';
})();
