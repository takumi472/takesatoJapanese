// 最低限PWAとして成立させるための空のサービスワーカー
self.addEventListener('install', (event) => {
    console.log('Service Worker: Installed');
});

self.addEventListener('activate', (event) => {
    console.log('Service Worker: Activated');
});

self.addEventListener('fetch', (event) => {
    // ここでキャッシュ制御を行いますが、最初は空でもPWA化可能です
});