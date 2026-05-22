import re
from typing import Optional

# 유튜브 자막 API는 pip install youtube-transcript-api 로 가상환경에 설치해야 사용 가능합니다.
# from youtube_transcript_api import YouTubeTranscriptApi

class YoutubeTranscriptExtractor:
    """
    [담당: 외부 API & 데이터 크롤링 엔지니어]
    유튜브 비디오에서 자막 스크립트를 로딩하여 지식 베이스에 구축 가능한 형태의 일반 자연어 텍스트로 정제합니다.
    """
    def __init__(self, video_id_or_url: str):
        self.video_id = self.extract_video_id(video_id_or_url)

    def extract_video_id(self, input_str: str) -> str:
        """URL 혹은 단순 ID 문자열에서 11자리 YouTube Video ID를 파싱해 냅니다."""
        # 11자리 비디오 ID 패턴 매칭
        pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:&|$|\?)"
        match = re.search(pattern, input_str)
        if match:
            return match.group(1)
        return input_str # 입력 자체가 ID인 경우 대비

    def get_clean_transcript(self) -> Optional[str]:
        """
        YouTubeTranscriptApi를 활용하여 한국어 자막을 추출하고, 
        각 타임라인 텍스트를 줄바꿈 및 문맥에 맞게 이어 붙여 자연어로 반환합니다.
        """
        if not self.video_id:
            return None
            
        print(f"🎬 유튜브 비디오 ID: {self.video_id} 로부터 자막 추출 진행 중...")
        
        # 뼈대 목업 리턴 (라이브러리 미설치 및 테스트 환경 우회용)
        mock_transcript = (
            "안녕하세요 면접왕 이형입니다. 오늘 신중년 여러분들과 함께 자소서 작성 팁에 대해 이야기해 보겠습니다. "
            "가장 많이 실수하시는 부분이 바로 성장과정에 '성실하게 자라왔다', '화목하게 자랐다' 같은 상투적인 문구를 적는 것입니다. "
            "인사담당자가 정말 궁금해하는 것은 여러분이 과거에 겪었던 아주 구체적인 프로젝트 해결 경험과 "
            "그 행동의 실질적인 수치적 결과입니다. 예를 들어, 생산 현장에서 부품 불량률을 5% 낮추기 위해 어떤 설비 교체 아이디어를 냈는지 "
            "자세한 STAR 구조로 서술해 주셔야 설득력을 얻습니다. 이 점을 반드시 기억하십시오."
        )

        try:
            # TODO: 실제 라이브러리 구동 로직 구현
            # transcript_list = YouTubeTranscriptApi.get_transcript(self.video_id, languages=['ko'])
            # full_text = " ".join([item['text'] for item in transcript_list])
            # return self.clean_transcript_text(full_text)
            pass
        except Exception as e:
            print(f"[Warning] 실제 유튜브 API 추출 실패 (목업 데이터 반환): {e}")
            
        return mock_transcript

    def clean_transcript_text(self, raw_text: str) -> str:
        """대괄호로 묶인 소리 묘사(예: [음악], [웃음]) 및 비정상적인 줄바꿈, 특수기호를 지워 정제합니다."""
        if not raw_text:
            return ""
        # 1. 괄호로 묶인 사운드 팁 제거
        text = re.sub(r'\[[^\]]*\]', '', raw_text)
        text = re.sub(r'\([^)]*\)', '', text)
        # 2. 다중 공백 제거
        text = " ".join(text.split())
        return text
