// 機能: identifier入力欄に値を設定し、送信ボタンをクリックします。
// 呼び出し元: set_identifier_input_and_submit 関数 (arim_rde_tool.py)

(function(){
    var input = document.getElementById('identifier');
    if(input) {
        input.value = '{value}';
        input.dispatchEvent(new Event('input', { bubbles: true }));
        var btn = document.getElementById('idp-discovery-submit') || document.querySelector('button[type=submit]');
        if(btn && !btn.disabled) {
            btn.click();
            return 'set_and_submitted';
        }
        return 'set_only';
    }
    return 'no_input';
})();
