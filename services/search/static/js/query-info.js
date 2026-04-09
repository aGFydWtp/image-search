/**
 * QueryInfo — クエリ解析結果（semantic_query、フィルタタグ）の可視化コンポーネント。
 */

let _el = null;

/**
 * QueryInfoを初期化する。
 */
export function initQueryInfo() {
  _el = document.getElementById("query-info");
}

/**
 * クエリ解析結果を描画する。
 * @param {Object} parsedQuery - ParsedQuery
 */
export function renderQueryInfo(parsedQuery) {
  if (!_el) return;

  const { semantic_query, filters } = parsedQuery;
  const hasMotif = filters.motif_tags && filters.motif_tags.length > 0;
  const hasColor = filters.color_tags && filters.color_tags.length > 0;

  // フィルタが空なら非表示
  if (!hasMotif && !hasColor) {
    _el.hidden = true;
    return;
  }

  _el.hidden = false;
  _el.innerHTML = "";

  const inner = document.createElement("div");
  inner.className = "query-info-inner";

  // semantic_query テキスト
  const queryText = document.createElement("span");
  queryText.textContent = `「${semantic_query}」`;
  inner.appendChild(queryText);

  // motif_tags バッジ（緑系）
  if (hasMotif) {
    for (const tag of filters.motif_tags) {
      const badge = document.createElement("span");
      badge.className = "badge badge-motif";
      badge.textContent = tag;
      inner.appendChild(badge);
    }
  }

  // color_tags バッジ（青系）
  if (hasColor) {
    for (const tag of filters.color_tags) {
      const badge = document.createElement("span");
      badge.className = "badge badge-color";
      badge.textContent = tag;
      inner.appendChild(badge);
    }
  }

  _el.appendChild(inner);
}

/**
 * QueryInfoを非表示にする。
 */
export function hideQueryInfo() {
  if (_el) {
    _el.hidden = true;
  }
}
