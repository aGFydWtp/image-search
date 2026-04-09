/**
 * ApiClient — Search APIへのfetchラッパー。
 * タイムアウト制御、エラー分類、前回リクエストキャンセルを提供する。
 */

const SEARCH_ENDPOINT = "/api/artworks/search";
const TIMEOUT_MS = 30000;

let _currentController = null;

/**
 * Search APIを呼び出す。
 * @param {string} query - 検索クエリ (1-500文字)
 * @param {number} [limit=24] - 取得件数 (1-100)
 * @returns {Promise<Object>} SearchResponse
 * @throws {ApiError}
 */
export async function search(query, limit = 24) {
  // 前回リクエストをキャンセル
  if (_currentController) {
    _currentController.abort();
  }

  const controller = new AbortController();
  _currentController = controller;

  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(SEARCH_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, limit }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      if (response.status >= 400 && response.status < 500) {
        throw new ApiError("検索条件を確認してください", response.status, detail);
      }
      throw new ApiError(
        "サーバーエラーが発生しました。しばらくしてから再試行してください",
        response.status,
        detail,
      );
    }

    return await response.json();
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (err.name === "AbortError") {
      throw new ApiError("接続がタイムアウトしました", 0);
    }
    throw new ApiError("ネットワーク接続を確認してください", 0);
  } finally {
    clearTimeout(timeoutId);
    if (_currentController === controller) {
      _currentController = null;
    }
  }
}

export class ApiError extends Error {
  /**
   * @param {string} message - ユーザー向けメッセージ
   * @param {number} status - HTTPステータス (0 = ネットワーク/タイムアウト)
   * @param {string} [detail] - サーバーからの詳細
   */
  constructor(message, status, detail = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
