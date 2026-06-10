document.addEventListener('DOMContentLoaded', () => {
    const zipInput = document.getElementById('zipcode'); // 郵便番号入力欄のID
    const addressInput = document.getElementById('address'); // 住所入力欄のID
    const loadingStatusElement = document.getElementById('address-loading-status'); // 検索状況表示用の要素のID (例: <span id="address-loading-status"></span>)

    if (!zipInput || !addressInput) {
        console.warn('郵便番号または住所の入力欄が見つかりませんでした。');
        return;
    }

    zipInput.addEventListener('input', async (e) => {
        // 数字以外を除去して7桁かチェック
        const zipcode = e.target.value.replace(/[^0-9]/g, '');
        
        // 以前の住所とステータスをクリア
        addressInput.value = '';
        if (loadingStatusElement) {
            loadingStatusElement.textContent = '';
            loadingStatusElement.style.color = ''; // 色をリセット
        }

        if (zipcode.length === 7) {
            if (loadingStatusElement) {
                loadingStatusElement.textContent = '検索中...';
                loadingStatusElement.style.color = 'gray'; // 検索中のメッセージの色
            }
            try {
                const response = await fetch(`https://zipcloud.ibsnet.co.jp/api/search?zipcode=${zipcode}`);
                const data = await response.json();
                
                if (data.status === 200 && data.results) {
                    const result = data.results[0];
                    // 住所がすでに入力されている場合は、確認後に上書き、あるいは自動補完
                    addressInput.value = `${result.address1}${result.address2}${result.address3}`;
                } else if (data.message) {
                    console.error('API Error:', data.message);
                    if (loadingStatusElement) {
                        loadingStatusElement.textContent = ''; // 成功時はメッセージをクリア
                    }
                } else {
                    // APIから結果が返されたが、住所が見つからない場合
                    if (loadingStatusElement) {
                        loadingStatusElement.textContent = '住所が見つかりませんでした。';
                        loadingStatusElement.style.color = 'red';
                    }
                    console.error('API Error or No Results:', data.message || 'No results found for zipcode:', zipcode);
                }
            } catch (error) {
                // ネットワークエラーなど、API呼び出し自体が失敗した場合
                if (loadingStatusElement) {
                    loadingStatusElement.textContent = '住所の取得に失敗しました。';
                    loadingStatusElement.style.color = 'red';
                }
                console.error('住所の取得に失敗しました:', error);
            }
        }
    });
});