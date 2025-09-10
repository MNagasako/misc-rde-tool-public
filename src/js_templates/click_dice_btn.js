// 機能: DICEボタンをクリックします。
// 呼び出し元: click_dice_btn 関数 (arim_rde_tool.py)

(function(){
    var btn = document.getElementById('EXGENIdPExchange');
    if(btn && btn.offsetParent !== null && !btn.disabled) {
        btn.click();
        return true;
    }
    return false;
})();
