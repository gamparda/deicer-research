# 제설제 탐구 완료 결과

외부 물 1 kg의 결빙 억제를 기준으로 NaCl과 CaCl2의 필요량·가격비·염화물 투입량·희석 한계를 계산했다. 공개된 실제 융빙 관측값도 재분석했다. 고2 수준의 핵심 설명을 담은 **3쪽 보고서**는 [PDF 보고서](탐구_결과보고서.pdf), [Word 보고서](탐구_결과보고서.docx), [본문 Markdown](탐구_결과보고서.md)에서 확인할 수 있다.

![물 1 kg을 -10°C에서 얼지 않는 농도로 만드는 데 필요한 양](outputs/08_report_comparison.png)

보고서는 농도와 어는점 내림, 간단한 계산 예시, 온도별 필요량과 비용 비교를 중심으로 정리했다. 소스 코드와 입력 자료의 GitHub 링크도 보고서 안에 넣었다. 상세 통계 결과는 저장소의 코드와 outputs/에서 확인할 수 있다.

## 실행

Python 3.10 이상에서 프로젝트 폴더로 이동하여 실행한다.

```bash
pip install -r requirements.txt
python analyze.py
python make_report.py
```

재실행은 outputs/의 계산 결과와 보고서를 다시 만든다. 실제 관측 원자료를 수정하거나 가상의 측정 오차를 추가하지 않는다.

배포본은 data/phase_points.csv의 정리된 물성값을 사용하므로 원문 사이트에 접속하지 않아도 재현된다. 원문 HTML/PDF 스냅샷이 모두 sources/에 있는 연구 작업본은 거기서 물성표를 다시 추출한다. 입력 CSV에는 출처 URL, 표 위치, 원래 단위와 값이 포함되어 있다.

## 핵심 결과와 기준

- 기본 자료: ASHRAE 2017 SI판의 순수 NaCl·CaCl2 물성표. 대안은 2025 NaCl 표와 OxyChem 2026 CaCl2 표다.
- 외부 물 1 kg, -10°C: NaCl 161.4 g, 무수 CaCl2 172.7 g, 순수 CaCl2·2H2O 242.4 g.
- 같은 조건에서 이수화물 제품의 가격이 NaCl의 약 0.666배일 때 재료비가 같다. 대안 자료에서는 약 0.787배다.
- 2025 구매 공고 예산 단가와 규격 하한을 적용한 시나리오에서 CaCl2/NaCl 비용비는 -10°C에서 약 2.10~2.70배다. 실제 납품 제품·현장 성능·낙찰가를 측정한 결과는 아니다.
- 염화물 투입량의 작은 우열은 물성 자료에 따라 바뀌었다.
- 0°F 준비 조건의 15분 시험에서 MgCl2 29% / CaCl2 32% 부피당 융빙량 비는 원문 선별 자료 1.233, 전체 자료 1.163이었다. NaCl은 준비 온도가 다르므로 직접 순위 비교에서 제외했다.

## 파일

- analyze.py: 자료 검증, 계산과 그림 7개, 계층 부트스트랩 30,000회.
- make_report.py: 계산 결과로 고2 수준의 3쪽 보고서(Markdown·Word·PDF)와 간단한 비교 그래프 생성.
- data/phase_points.csv: 물성 131행. 서로 다른 출처·단위판의 값을 구분한다.
- data/imc_observations.csv: 실제 공개 관측값 120개와 원문 선별 플래그.
- data/purchase_notice.json: 구매 공고의 예산·질량·규격 하한 전사와 접근 한계.
- data/budget_prices.csv: 공고 수량과 예산에서 계산한 단가.
- outputs/key_results.csv: 주요 네 온도의 결과.
- outputs/equilibrium_grid.csv: 151개 온도 × 3개 자료 조건의 계산 결과. 실험 453회를 뜻하지 않는다.
- outputs/budget_application.csv: 제품 조성 가정을 구분한 예산 단가 적용 결과.
- outputs/equal_budget_dilution.csv: 같은 kg당 가격·250 g 투입 조건의 희석 한계.
- outputs/imc_bootstrap.csv, imc_leave_one_group_out.csv: 실제 관측값의 자료 내 안정성 분석.
- outputs/data_audit.json: 사용·보류·제외한 자료와 이유.
- outputs/input_sha256.json: 입력 파일 해시.
- sources/NanumGothic-Regular.ttf 및 OFL.txt: 그림과 PDF의 한글 표시를 위한 글꼴과 라이선스.

전체 분석은 문헌 데이터 재분석·수치 계산이다. 자료 수집, 코드 작성과 실행에 AI 도구를 사용했다. 자체 물리 실험을 수행한 것으로 표시하지 않는다. 보고서의 범위와 조성 가정을 함께 읽어야 결과를 정확히 사용할 수 있다.
