"""Reranker: ベクトル検索結果に対し軽量スコア合成でリランキングする。"""

from shared.models.search import ParsedQuery, SearchResultItem
from shared.qdrant.repository import SearchResult

# スコア合成の重み
_W_VECTOR = 0.65
_W_MOTIF = 0.15
_W_COLOR = 0.10
_W_BRIGHTNESS = 0.05
_W_FREEFORM = 0.05


class Reranker:
    """ベクトル類似度 + payloadメタデータのスコア合成リランカー。"""

    def rerank(
        self,
        candidates: list[SearchResult],
        parsed_query: ParsedQuery,
    ) -> list[SearchResultItem]:
        """候補をリランキングし、SearchResultItemリストを返す。"""
        scored = []
        for candidate in candidates:
            motif_score = self._calc_motif_match(candidate, parsed_query)
            color_score = self._calc_color_match(candidate, parsed_query)
            brightness_score = self._calc_brightness_affinity(candidate, parsed_query)
            freeform_score = self._calc_freeform_match(candidate, parsed_query)

            final = (
                _W_VECTOR * candidate.score
                + _W_MOTIF * motif_score
                + _W_COLOR * color_score
                + _W_BRIGHTNESS * brightness_score
                + _W_FREEFORM * freeform_score
            )
            final = max(0.0, min(1.0, final))

            reasons = self._build_reasons(
                candidate, parsed_query, motif_score, color_score, brightness_score,
                freeform_score,
            )

            scored.append(
                SearchResultItem(
                    artwork_id=candidate.artwork_id,
                    title=candidate.title,
                    artist_name=candidate.artist_name,
                    thumbnail_url=candidate.thumbnail_url,
                    score=round(final, 4),
                    match_reasons=reasons,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _calc_motif_match(self, candidate: SearchResult, query: ParsedQuery) -> float:
        """motif_tagsの一致度 (0.0-1.0)。"""
        query_motifs = set(query.filters.motif_tags)
        if not query_motifs:
            return 0.0
        result_motifs = set(candidate.payload.get("motif_tags", []))
        matched = query_motifs & result_motifs
        return len(matched) / len(query_motifs)

    def _calc_color_match(self, candidate: SearchResult, query: ParsedQuery) -> float:
        """color_tagsの一致度 (0.0-1.0)。"""
        query_colors = set(query.filters.color_tags)
        if not query_colors:
            return 0.0
        result_colors = set(candidate.payload.get("color_tags", []))
        matched = query_colors & result_colors
        return len(matched) / len(query_colors)

    def _calc_freeform_match(self, candidate: SearchResult, query: ParsedQuery) -> float:
        """freeform_keywordsとクエリ語のマッチ度 (0.0-1.0)。"""
        freeform = set(candidate.payload.get("freeform_keywords", []))
        if not freeform:
            return 0.0
        query_tokens = set(query.semantic_query.lower().split())
        if not query_tokens:
            return 0.0
        matched = query_tokens & freeform
        return len(matched) / len(query_tokens)

    def _calc_brightness_affinity(self, candidate: SearchResult, query: ParsedQuery) -> float:
        """brightness boostとの近接度 (0.0-1.0)。"""
        if query.boosts.brightness_min is None:
            return 0.0
        result_brightness = candidate.payload.get("brightness_score", 0.5)
        target = query.boosts.brightness_min
        distance = abs(result_brightness - target)
        return max(0.0, 1.0 - distance)

    def _build_reasons(
        self,
        candidate: SearchResult,
        query: ParsedQuery,
        motif_score: float,
        color_score: float,
        brightness_score: float,
        freeform_score: float = 0.0,
    ) -> list[str]:
        """ヒット理由の自然言語リストを生成する。"""
        reasons: list[str] = []

        # セマンティック類似度
        if candidate.score >= 0.5:
            reasons.append("雰囲気が近い")

        # モチーフ一致
        if motif_score > 0:
            query_motifs = set(query.filters.motif_tags)
            result_motifs = set(candidate.payload.get("motif_tags", []))
            matched = query_motifs & result_motifs
            for m in matched:
                reasons.append(f"{m}モチーフ一致")

        # 色一致
        if color_score > 0:
            query_colors = set(query.filters.color_tags)
            result_colors = set(candidate.payload.get("color_tags", []))
            matched = query_colors & result_colors
            for c in matched:
                reasons.append(f"{c}色一致")

        # 明るさ近接
        if brightness_score > 0.7:
            reasons.append("明るさが近い")

        # freeform キーワード一致
        if freeform_score > 0:
            reasons.append("キーワード一致")

        return reasons
