const { test, expect } = require('@playwright/test');

/**
 * E2Eテスト：画面遷移テスト
 * 
 * テストの目的：
 * 1. ログインが正常に完了し、ダッシュボードにリダイレクトされること。
 * 2. ダッシュボードから主要なページ（生徒一覧、スタッフ一覧など）へ正しく遷移できること。
 * 3. ログアウトが正常に機能し、ログインページに戻ること。
 * 
 * 前提条件：
 * - Playwrightの設定ファイル(playwright.config.js)で `baseURL` が設定されていること。
 *   例: `baseURL: 'http://127.0.0.1:5000'`
 * - `TEST_USER` と `TEST_PASS` に有効なテスト用アカウント情報が設定されていること。
 */
test.describe('画面遷移テスト (Navigation Test)', () => {

  // --- テスト用のユーザー情報 (実際のテストアカウントに置き換えてください) ---
  const TEST_USER = 'admin@example.com'; 
  const TEST_PASS = 'password';      

  // 各テストの前に、ログイン処理を共通化
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('ユーザー名またはメールアドレス').fill(TEST_USER);
    await page.getByPlaceholder('パスワード').fill(TEST_PASS);
    await page.getByRole('button', { name: 'ログイン' }).click();
    
    // ログイン後、ダッシュボードにいることを確認
    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByRole('heading', { name: '管理システム' })).toBeVisible();
  });

  test('ダッシュボードから各ページへ正常に遷移できること', async ({ page }) => {
    
    // 1. 受講生一覧へ遷移
    await page.getByRole('link', { name: '受講生一覧' }).click();
    await expect(page).toHaveURL('/student/');
    await expect(page.getByRole('heading', { name: '武里日本語教室 受講生一覧' })).toBeVisible();

    // 2. スタッフ一覧へ遷移
    await page.getByRole('link', { name: 'スタッフ一覧' }).click();
    await expect(page).toHaveURL('/staff/');
    await expect(page.getByRole('heading', { name: '武里日本語教室 スタッフ一覧' })).toBeVisible();

    // 3. スタッフミーティング一覧へ遷移
    await page.getByRole('link', { name: 'スタッフミーティング' }).click();
    await expect(page).toHaveURL('/meeting/');
    await expect(page.getByRole('heading', { name: 'スタッフミーティング議事録' })).toBeVisible();

    // 4. 出席リストへ遷移
    await page.getByRole('link', { name: '出席リスト' }).click();
    await expect(page).toHaveURL(/.*\/student\/attendance/); // URLに /student/attendance が含まれることを確認
    await expect(page.getByRole('heading', { name: '出席リスト' })).toBeVisible();

    // 5. マニュアルページへ遷移 (ダッシュボードに戻ってから)
    await page.goto('/dashboard');
    // '使い方マニュアル' ボタンを探してクリック
    const manualLink = page.getByRole('link', { name: /使い方マニュアル/ });
    if (await manualLink.isVisible()) {
        await manualLink.click();
        await expect(page).toHaveURL('/manual');
        await expect(page.getByRole('heading', { name: 'アプリケーションマニュアル' })).toBeVisible();
    } else {
        console.warn('マニュアルページへのリンクがダッシュボードに見つかりませんでした。');
    }
  });

  test('ログアウトが正常に機能すること', async ({ page }) => {
    // ダッシュボードにいることを確認
    await expect(page).toHaveURL('/dashboard');

    // ログアウトボタンをクリック
    await page.getByRole('link', { name: 'ログアウト' }).click();

    // ログアウト後、ログインページにリダイレクトされていることを確認
    await expect(page).toHaveURL('/login');
    await expect(page.getByText('ログアウトしました。')).toBeVisible();
  });
});