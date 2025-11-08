// エラーページ検出JavaScript
(function() {
    var bodyText = document.body.innerText || document.body.textContent || '';
    var titleText = document.title || '';
    
    // 401エラーやエラーページの検出
    var is401 = bodyText.indexOf('401') !== -1 || 
                bodyText.indexOf('HTTP ERROR 401') !== -1 ||
                titleText.indexOf('401') !== -1;
    
    var isError = bodyText.indexOf('このページは動作していません') !== -1 ||
                  bodyText.indexOf('エラー') !== -1 ||
                  bodyText.indexOf('Error') !== -1;
    
    return {
        is401: is401,
        isError: isError,
        url: window.location.href,
        title: titleText,
        bodyPreview: bodyText.substring(0, 200)
    };
})();
