// 機能: identifier入力欄の状態をポーリングして準備完了を確認します。
// 呼び出し元: poll_identifier_input 関数 (arim_rde_tool.py)

(function(){
    var input = document.getElementById('identifier');
    if(input && input.offsetParent !== null && !input.disabled) return true;
    return false;
})();
