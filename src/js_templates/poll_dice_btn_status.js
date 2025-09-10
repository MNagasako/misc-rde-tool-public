// 機能: DICEボタンの状態をポーリングして準備完了を確認します。
// 呼び出し元: poll_dice_btn_status 関数 (arim_rde_tool.py)

(function(){
    var btn = document.getElementById('EXGENIdPExchange');
    if(btn && btn.offsetParent !== null && !btn.disabled) return true;
    return false;
})();
