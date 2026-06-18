"""
gemini_client.py
Gemini API 호출 - 노트북에 명시된 cascade 패턴:
- gemini-3.1-flash-lite (1순위)
- gemini-2.5-flash-lite (폴백, 429/RESOURCE_EXHAUSTED 시)

공시 BODY 텍스트 -> 구조화된 JSON (Pydantic 스키마)
"""
from __future__ import annotations
import logging
import time
from typing import Optional

import truststore
truststore.inject_into_ssl()

from google import genai
import google.genai.types as gt
from pydantic import BaseModel, Field

from config import GEMINI_API_KEY

log = logging.getLogger(__name__)

# 노트북 명시 모델 순서
GEMINI_MODELS = ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
MAX_RETRIES_PER_MODEL = 3


# ─────────────────────────────────────────────────
# 출력 스키마
# ─────────────────────────────────────────────────
class ContractAIFields(BaseModel):
    """공시 본문에서 추출 + AI 분석 결과"""
    counterparty: str = Field(description="계약 상대방 회사명. 명시 안 됐으면 빈 문자열.")
    amount_won:   Optional[int] = Field(default=None, description="계약 금액 (원 단위 정수). 명시 안 됐으면 null.")
    revenue_ratio: Optional[float] = Field(default=None, description="매출액 대비 비율(%). 명시 안 됐으면 null.")
    period_start: str = Field(default="", description="계약 시작일 YYYY-MM-DD. 명시 안 됐으면 빈 문자열.")
    period_end:   str = Field(default="", description="계약 종료일 YYYY-MM-DD. 명시 안 됐으면 빈 문자열.")
    ai_importance: int = Field(
        description="중요도 1~5. 평가 기준: 매출비중·계약상대방·계약규모·기업규모를 종합. "
                    "5=경영진 즉시보고급, 4=섹터 영향, 3=평균적 호재, 2=소규모, 1=루틴/미미."
    )
    ai_summary:    str = Field(description="2~3문장의 한국어 핵심 요약. 숫자/상대방 포함.")


# ─────────────────────────────────────────────────
# 프롬프트
# ─────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국 주식시장 공시 분석가입니다.
'단일판매ㆍ공급계약체결' 공시 원문을 받아 다음 정보를 추출하고 분석합니다.

규칙:
1. 원문에 명시된 사실만 추출. 추측 금지.
2. 금액은 원 단위 정수로. '억원' 표기는 곱셈해서 환산.
3. 매출비중은 % 숫자만(소수점 둘째자리). '최근 매출액 대비' 비율.
4. 중요도(ai_importance)는 다음 기준으로 1~5 정수:
   - 5: 매출비중 30% 이상 OR 글로벌 빅테크 신규계약 OR 회사 분기실적 가이드 변경 수준
   - 4: 매출비중 10~30% OR 신사업/신규고객 진입
   - 3: 매출비중 3~10%, 통상적인 신규 수주
   - 2: 매출비중 1~3%, 소규모
   - 1: 매출비중 1% 미만 또는 미미한 정정
5. ai_summary는 2~3문장. '누가/누구에게/얼마/매출비중/특이사항' 위주.
6. JSON 스키마만 출력. 다른 텍스트 금지.
"""

USER_TEMPLATE = """[공시 제목]
{title}

[공시 본문]
{body}
"""


# ─────────────────────────────────────────────────
# 클라이언트
# ─────────────────────────────────────────────────
class GeminiClient:
    def __init__(self):
        self.client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=gt.HttpOptions(client_args={"verify": False}),
        )

    def analyze_contract(self, title: str, body: str) -> Optional[ContractAIFields]:
        """공시 1건 분석. 실패 시 None."""
        if not body or len(body.strip()) < 50:
            log.warning("  BODY 너무 짧음, 분석 스킵")
            return None

        prompt = USER_TEMPLATE.format(title=title, body=body[:30000])  # 토큰 폭주 방지 컷

        for model in GEMINI_MODELS:
            for attempt in range(MAX_RETRIES_PER_MODEL):
                try:
                    res = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=gt.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=ContractAIFields,
                            temperature=0.2,
                        ),
                    )
                    return ContractAIFields.model_validate_json(res.text)
                except Exception as e:
                    msg = str(e)
                    is_quota = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower()
                    log.warning(
                        f"  Gemini {model} 실패 (attempt {attempt+1}/{MAX_RETRIES_PER_MODEL}): {msg[:200]}"
                    )
                    if is_quota:
                        # quota면 같은 모델 재시도 무의미 → 다음 모델로
                        log.info(f"  -> quota 감지, 다음 모델로 폴백")
                        break
                    time.sleep(1.5 ** attempt)

        log.error("  모든 Gemini 모델 실패")
        return None
