/**
 * ResultCard — 個別検索結果アイテムの表示コンポーネント。
 */

const PLACEHOLDER_SRC = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect fill='%23e0e0e0' width='400' height='300'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-size='14'%3ENo Image%3C/text%3E%3C/svg%3E";

/** http: / https: スキームのみ許可する。 */
function isSafeUrl(url) {
  try {
    const u = new URL(url, location.href);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch { return false; }
}

/**
 * 検索結果アイテムからカードDOM要素を生成する。
 * @param {Object} item - SearchResultItem
 * @returns {HTMLElement}
 */
export function createResultCard(item) {
  const card = document.createElement("div");
  card.className = "result-card";

  // サムネイル画像
  const img = document.createElement("img");
  img.className = "result-card-image";
  img.src = isSafeUrl(item.thumbnail_url) ? item.thumbnail_url : PLACEHOLDER_SRC;
  img.alt = item.title ?? "";
  img.loading = "lazy";
  img.onerror = () => {
    img.src = PLACEHOLDER_SRC;
  };
  card.appendChild(img);

  // カードボディ
  const body = document.createElement("div");
  body.className = "result-card-body";

  const title = document.createElement("div");
  title.className = "result-card-title";
  title.textContent = item.title ?? "";
  body.appendChild(title);

  const artist = document.createElement("div");
  artist.className = "result-card-artist";
  artist.textContent = item.artist_name ?? "";
  body.appendChild(artist);

  // match_reasons バッジ
  if (item.match_reasons && item.match_reasons.length > 0) {
    const reasons = document.createElement("div");
    reasons.className = "result-card-reasons";
    for (const reason of item.match_reasons) {
      const badge = document.createElement("span");
      badge.className = "badge badge-reason";
      badge.textContent = reason;
      reasons.appendChild(badge);
    }
    body.appendChild(reasons);
  }

  card.appendChild(body);

  // ホバー/タップ オーバーレイ（スコア詳細）
  const overlay = document.createElement("div");
  overlay.className = "result-card-overlay";

  const scoreEl = document.createElement("div");
  scoreEl.className = "score";
  scoreEl.textContent = typeof item.score === "number" ? item.score.toFixed(3) : "—";
  overlay.appendChild(scoreEl);

  if (item.match_reasons && item.match_reasons.length > 0) {
    const list = document.createElement("ul");
    list.className = "reasons-list";
    for (const reason of item.match_reasons) {
      const li = document.createElement("li");
      li.textContent = reason;
      list.appendChild(li);
    }
    overlay.appendChild(list);
  }

  card.appendChild(overlay);

  // モバイル: タップでオーバーレイ表示切り替え
  card.addEventListener("click", () => {
    overlay.classList.toggle("active");
  });

  return card;
}
