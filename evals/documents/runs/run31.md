# Run 31 — third holdout: two long survey and tutorial papers

Profile: fast | Model: qwen3:8b | Vision: qwen3-vl:8b-instruct | Image planner: qwen3:14b | Documents: qwen3:14b | Code: 416364e + uncommitted changes
Cases: 27 | Total: 32.3 min

Grades: ✅ 15, ⚠️ 5, ❌ 4, pass 3

Each answer is printed below as the agent gave it, with the expected answer from the case file and the grade.

| Case | Grade | Reason |
|---|---|---|
| SA1 | ⚠️ | Both gains named, but integration gain explained as higher performance and less interference instead of shared resources; coordination gain from a networked-sensing example |
| SA2 | ✅ | Found by the second search after a first 'not covered' |
| SA3 | ✅ | Correct |
| SA4 | ✅ | Correct |
| SA5 | ✅ | Correct |
| SA6 | ✅ | Correct |
| SA7 | ✅ | Correct |
| SA8 | ✅ | Correct |
| SA9 | ✅ | Correct |
| SA10 | ✅ | Correct |
| SA11 | ✅ | Correct |
| SA12 | ⚠️ | Sec. V described as 'more on signal processing' instead of receive signal processing; Sec. VIII left out |
| SH1 | pass | Not in the document |
| SH2 | pass | Not in the document |
| RA1 | ⚠️ | 'The physical medium' from p.13; leaves out that it is seen as uncontrollable and that the RIS extends protocol design to it (p.2) |
| RA2 | ❌ | False 'not in the document' after the second search; the answer is on p.17 |
| RA3 | ✅ | Correct |
| RA4 | ❌ | False 'not in the document'; the answer is on p.23 |
| RA5 | ❌ | Says the percentage is not given; the NLOS part (4% in the narrowband case) is right |
| RA6 | ⚠️ | Content right, but expands RIS as 'Reflective Intelligent Surface', a name the paper never uses |
| RA7 | ❌ | 'At the receiver' right but cited to p.7; 'sufficient to estimate h(t)' is wrong (the paper: the cascade matrix V, p.24) |
| RA8 | ✅ | Correct |
| RA9 | ✅ | Correct |
| RA10 | ✅ | Correct |
| RA11 | ✅ | Correct; the warning that p.16 was not read is accurate |
| RA12 | ⚠️ | 929 s (26 parts); PEB expanded as 'Predicted Error Bound' (it is the position error bound) |
| RH1 | pass | Not in the document |

## SA1 — ⚠️

**File:** isac_survey.pdf  
**Question:** ISAC 논문에서 정의한 두 가지 이득(gain)은 무엇이고 각각 어떻게 얻어져?  
**Expected:** Integration gain from the shared use of wireless resources for both S&C; coordination gain from the mutual assistance between S&C. (pages 4)  
**Grade:** ⚠️ Both gains named, but integration gain explained as higher performance and less interference instead of shared resources; coordination gain from a networked-sensing example

**Answer:**

> ISAC 논문에서 정의한 두 가지 이득(gain)은 다음과 같습니다:
>
> 1. **Integration Gain**:
>    - 이 이득은 통합된 감지와 통신 기능을 통해 얻어집니다. ISAC 시스템은 통신과 감지 기능을 하나의 시스템으로 통합함으로써, 각각의 기능을 별도로 수행하는 시스템보다 더 높은 성능을 달성할 수 있습니다. 이는 통신과 감지 간의 협업을 통해 상호 간섭을 줄이고, 자원을 효율적으로 사용할 수 있기 때문입니다 [p.4].
>
> 2. **Coordination Gain**:
>    - 이 이득은 감지와 통신 간의 협업을 통해 얻어집니다. 예를 들어, 네트워크 감지에서 다중 RRH(remotely radio head)가 협력하여 동일한 목표를 감지할 때, 서로 다른 방향에서의 감지 정보를 활용하여 타겟의 레이더 산란단면적(RCS) 변동을 보상할 수 있습니다. 이는 감지 성능에 대한 협업 이득을 제공하며, 이는 MIMO 통신에서의 다중 경로 이득과 유사합니다 [p.26].
>
> 출처: p.4 (7. Human Computer), p.26 (TABLE IV)

## SA2 — ✅

**File:** isac_survey.pdf  
**Question:** IEEE 802.11bf는 언제 만들어졌고, 무엇을 목표로 해?  
**Expected:** Task group created in 2020 (the topic interest group and study group in 2019) to modify Wi-Fi standards to enhance sensing with 802.11-compliant waveforms. (pages 9)  
**Grade:** ✅ Found by the second search after a first 'not covered'

**Answer:**

> IEEE 802.11bf는 2020년에 만들어졌으며, 기존의 Wi-Fi 표준에 적절한 수정을 통해 802.11 호환 파형을 사용하여 감지 능력을 향상시키는 것을 목표로 합니다 [p.9].
>
> 출처: p.9 (systems, gesture-based touchless interaction may s)

## SA3 — ✅

**File:** isac_survey.pdf  
**Question:** What did Huawei identify in November 2020, and what is the main focus of that technology?  
**Expected:** Harmonized sensing and communication as one of three new scenarios in 5.5G; exploits the sensing capability of existing massive MIMO base stations and supports UAVs and vehicles. (pages 9)  
**Grade:** ✅ Correct

**Answer:**

> In November 2020, Huawei identified harmonized sensing and communication as one of the three new scenarios in 5.5G (a.k.a. B5G) [91]. The main focus of this new technology is to exploit the sensing capability of the existing massive MIMO BS, and to support future UAVs and automotive vehicles [p.9].
>
> Sources: p.9 (CASE STUDIES AND KEY PERFORMANCE INDICATORS)

## SA4 — ✅

**File:** isac_survey.pdf  
**Question:** 5G NR Release 17 KPI에서 요구하는 가장 높은 측위 정확도는 얼마라고 했어?  
**Expected:** 0.2 m horizontally and 1 m vertically in industrial IoT applications. The sentence runs across the page break. (pages 5, 6)  
**Grade:** ✅ Correct

**Answer:**

> 5G NR Release 17 KPI에서 요구하는 가장 높은 측위 정확도는 수평으로 0.2 m, 수직으로 1 m라고 했어 [p.5].
>
> 출처: p.5 (EXISTING OVERVIEW PAPERS ON ISAC)

## SA5 — ✅

**File:** isac_survey.pdf  
**Question:** 표 II에서 Drone Monitoring and Management의 최대 거리와 최대 속도는 얼마야?  
**Expected:** Max. range 500 m, max. velocity 40 m/s. (pages 7)  
**Grade:** ✅ Correct

**Answer:**

> 표 II에서 "Drone Monitoring and Management"의 최대 거리는 500m이고, 최대 속도는 40 m/s입니다 [p.7].
>
> 출처: p.7 (CASE STUDIES AND KEY PERFORMANCE INDICATORS)

## SA6 — ✅

**File:** isac_survey.pdf  
**Question:** In Table II, what maximum range and maximum velocity are listed for Fall Detection and for Sleep Monitoring?  
**Expected:** Fall Detection: 10 m, 3 m/s. Sleep Monitoring: 1 m, 2 m/s. (pages 7)  
**Grade:** ✅ Correct

**Answer:**

> In Table II, the maximum range and maximum velocity for Fall Detection are listed as 10 meters and 3 m/s, respectively [p.7]. For Sleep Monitoring, the maximum range and maximum velocity are listed as 1 meter and 2 m/s, respectively [p.7].
>
> Sources: p.7 (CASE STUDIES AND KEY PERFORMANCE INDICATORS)

## SA7 — ✅

**File:** isac_survey.pdf  
**Question:** In the joint design example of Fig. 11, how many transmit antennas, what target angle, what false-alarm probability and what receive SNR are assumed?  
**Expected:** Nt = 16 (K = 4, 6, 8 users), target at 36 degrees, CFAR with false-alarm probability 10^-7 and receive SNR -6 dB. (pages 20)  
**Grade:** ✅ Correct

**Answer:**

> In the joint design example of Fig. 11, the number of transmit antennas assumed is 16 [p.20]. The target angle assumed is 36◦ [p.20]. The false-alarm probability assumed is 10−7 [p.20]. The receive SNR assumed is −6 dB [p.20].
>
> Sources: p.20 (ISAC WAVEFORM DESIGNS)

## SA8 — ✅

**File:** isac_survey.pdf  
**Question:** 식 (55)에서 ρ = 1이면 어떤 신호가 해가 되고, 그 의미는 뭐야?  
**Expected:** Communication gets full priority and the solution is the zero-forcing precoded signal for the channel H. (The paper writes ρ = 1 for both extremes; the sensing case means ρ = 0, giving X = X0.) (pages 20)  
**Grade:** ✅ Correct

**Answer:**

> 식 (55)에서 ρ = 1이면, 통신에 대한 우선순위가 완전히 주어지며, 문제 (55)의 해는 채널 H에 대한 제로 포싱 (ZF)_precoded 신호가 된다 [p.20]. 이는 통신 성능을 최적화하기 위해 감지 기능에 대한 우선순위를 완전히 무시하고, 통신에만 집중하는 경우를 의미한다.
>
> 출처: p.20 (ISAC WAVEFORM DESIGNS)

## SA9 — ✅

**File:** isac_survey.pdf  
**Question:** Fig. 13에서 μ = 4일 때 두 슬롯은 몇 개의 OFDM 심볼이고, SSB는 몇 개이며 각 SSB는 몇 심볼을 차지하고 무엇으로 구성돼?  
**Expected:** 28 OFDM symbols; 4 SSBs, each 4 OFDM symbols; PSS, SSS, PBCH and PBCH-DMRS. (pages 23)  
**Grade:** ✅ Correct

**Answer:**

> Fig. 13에서 μ = 4일 때 두 슬롯은 28개의 OFDM 심볼을 차지한다 [p.23]. SSB는 4개이며, 각 SSB는 4개의 OFDM 심볼을 차지한다 [p.23]. 각 SSB는 Primary Synchronization Signal (PSS), Secondary Synchronization Signal (SSS), Physical Broadcast Channel (PBCH), 그리고 PBCH-DMRS로 구성된다 [p.23].
>
> 출처: p.23 (PBCH-DMRS)

## SA10 — ✅

**File:** isac_survey.pdf  
**Question:** In the V2I beam tracking example (Fig. 17), how many antennas does the RSU have, what are the vehicle's distance and speed, and when does the ABP scheme lose track?  
**Expected:** 64-antenna RSU; vehicle at 25 m driving at 18 m/s; ABP rate drops to zero at 1040 ms while EKF-ISAC stays stable. (pages 28)  
**Grade:** ✅ Correct

**Answer:**

> In the V2I beam tracking example (Fig. 17), the RSU has 64 antennas [p.28]. The vehicle's distance is 25 meters, and its speed is 18 m/s [p.28]. The ABP scheme loses track of the vehicle's angle at 1040 ms [p.28].
>
> Sources: p.28 (ISAC RSU)

## SA11 — ✅

**File:** isac_survey.pdf  
**Question:** 기존 V2I 핸드오버 프로토콜은 어떻게 동작해?  
**Expected:** Dual-connection: the vehicle is connected to a serving and an idle RSU; if SINR_serve < SINR_idle, the serving RSU hands over and forwards the buffered data. (pages 29)  
**Grade:** ✅ Correct

**Answer:**

> 기존 V2I 핸드오버 프로토콜은 차량이 한 셀에서 다른 셀로 이동할 때, 지속적인 통신 서비스를 제공하기 위해 RSU 간의 핸드오버가 필요하다 [p.29]. 이 핸드오버 프로토콜은 이중 연결 기술(dual-connection techniques)에 기반한다 [p.29]. 이 기술은 차량이 현재 서비스 중인 RSU와 비활성 상태의 RSU와 동시에 연결되도록 한다 [p.29]. 두 링크의 QoS는 수신 SINR(Signal-to-Interference-plus-Noise Ratio)로 측정되며, 이는 SINRserve와 SINRidle로 나타난다 [p.29]. 차량이 차단되거나 거리가 멀어져 SINRserve < SINRidle이 되면, 서비스 중인 RSU는 핸드오버를 수행하고 버퍼링된 데이터를 비활성 상태의 RSU로 전달한다 [p.29]. 차량의 고속 이동으로 인해 빈번한 핸드오버와 재연결이 필요하며, 이는 추가적인 무선 자원을 소모한다 [p.29].
>
> 출처: p.29 (EKF-ISAC)

## SA12 — ⚠️

**File:** isac_survey.pdf  
**Question:** 이 논문의 전체 구성을 섹션별로 요약해 줘.  
**Expected:** Applications and industry (II), performance tradeoffs (III), waveform design (IV), receive signal processing (V), communication-assisted sensing / perceptive network (VI), sensing-assisted communications (VII), ISAC with other technologies (VIII).  
**Grade:** ⚠️ Sec. V described as 'more on signal processing' instead of receive signal processing; Sec. VIII left out

**Answer:**

> 이 논문은 ISAC 기술의 이론적 프레임워크에 대한 포괄적인 기술적 개요를 제공한다. 논문의 구조는 다음과 같다:
>
> 1. **Sec. II**: ISAC와 관련된 사용 사례 및 산업 활동을 연구한다 [p.5].
> 2. **Sec. III**: S&C 간의 성능 트레이드오프에 대한 이론적 한계, 물리 계층(PHY) 및 ISAC 채널에서의 트레이드오프, 그리고 크로스 레이어 설계에서의 트레이드오프를 살펴본다 [p.5].
> 3. **Sec. IV**: ISAC의 신호 처리 측면, 예를 들어 ISAC 파형 설계 및 수신 신호 처리를 다룬다 [p.5].
> 4. **Sec. V**: ISAC의 신호 처리 측면에 대한 추가적인 내용을 다룬다 [p.5].
> 5. **Sec. VI**: 통신 지원 감지(communication-assisted sensing)에 대한 설계를 논의한다 [p.5].
> 6. **Sec. VII**: 감지 지원 통신(sensing-assisted communications)에 대한 설계를 논의한다. 이는 감지 지원 빔 트레이닝, 빔 추적 및 일반적인 자원 할당을 포함한다 [p.5].
>
> 출처: p.5 (4. Smart Manufacturing)

## SH1 — pass

**File:** isac_survey.pdf  
**Question:** What market size in US dollars does the paper forecast for ISAC by 2030?  
**Expected:** No market figures in the paper.  
**Grade:** pass Not in the document

**Answer:**

> The document does not cover the market size in US dollars for ISAC by 2030.
>
> (The answer says the document does not cover this. Pages checked: p.3, p.4, p.5, p.6, p.9, p.12, p.30, p.34)

## SH2 — pass

**File:** isac_survey.pdf  
**Question:** 논문에서 3GPP Release 21의 ISAC 표준화 일정은 언제라고 했어?  
**Expected:** Release 21 is not mentioned (Release 16 and 17 are).  
**Grade:** pass Not in the document

**Answer:**

> 논문에서 3GPP Release 21의 ISAC 표준화 일정에 대한 정보는 제공되지 않았습니다. 문서는 3GPP Release 15, 16에 대한 내용을 다루고 있지만, Release 21에 대한 언급은 없습니다. [p.23]
>
> 출처: p.23 (240)

## RA1 — ⚠️

**File:** ris_tutorial.pdf  
**Question:** RIS 논문에서 말하는 Layer 0가 뭐고, RIS가 그걸 어떻게 바꿔?  
**Expected:** The wireless medium between transmitter and receiver, seen as uncontrollable and decided by nature; RIS extends the protocol design to Layer 0. (pages 2)  
**Grade:** ⚠️ 'The physical medium' from p.13; leaves out that it is seen as uncontrollable and that the RIS extends protocol design to it (p.2)

**Answer:**

> Layer 0은 물리적 전송 매체, 즉 무선 중계 환경을 의미합니다 [p.13]. RIS는 이 Layer 0의 환경을 조절하여 신호의 전파 환경을 영향을 미칩니다 [p.13]. RIS는 무선 신호를 반사하면서, 이 반사 과정을 통해 Layer 0의 환경을 조절합니다 [p.13]. RIS는 제어 정보를 기반으로 자신의 구성(θ)을 조정함으로써, Layer 0의 환경을 변화시킵니다 [p.13]. 이는 Layer 0의 환경이 RIS의 구성에 따라 달라지게 되는 것을 의미합니다 [p.13].
>
> 출처: p.13 (If any of the above assumptions are violated (e.g.)

## RA2 — ❌

**File:** ris_tutorial.pdf  
**Question:** With only four phase-shift configurations per RIS element, how large is the SNR loss?  
**Expected:** About 8/π² = -0.9 dB, so a small number of configurations per element is sufficient. (pages 17)  
**Grade:** ❌ False 'not in the document' after the second search; the answer is on p.17

**Answer:**

> The document does not cover the specific SNR loss associated with having only four phase-shift configurations per RIS element.
>
> (The answer says the document does not cover this. Pages checked: p.7, p.10, p.11, p.16, p.21, p.35, p.36)

## RA3 — ✅

**File:** ris_tutorial.pdf  
**Question:** Fig. 4 설정에서 대역폭은 얼마고, 직접 채널이 약할 때와 강할 때 RIS 경로가 직접 채널만큼 강해지려면 소자가 각각 몇 개 필요해?  
**Expected:** B = 1 MHz; weak direct channel (-110 dB): N = 32; strong (-80 dB): N = 1000. The SNR via the RIS grows as N^2. (pages 17)  
**Grade:** ✅ Correct

**Answer:**

> Fig. 4 설정에서 대역폭은 1 MHz입니다 [p.17]. 직접 채널이 약할 때, RIS 경로가 직접 채널만큼 강해지려면 32개의 소자가 필요합니다 [p.17]. 직접 채널이 강할 때, RIS 경로가 직접 채널만큼 강해지려면 1000개의 소자가 필요합니다 [p.17].
>
> 출처: p.17 (need to select the delays as τθn = (τd − τn,a − τn)

## RA4 — ❌

**File:** ris_tutorial.pdf  
**Question:** In the wideband simulation of Fig. 6, what are the carrier frequency, the RIS size, the number of elements and the subcarrier spacing?  
**Expected:** 3 GHz, 0.5 × 0.5 m, N = 400 elements of λ/4 × λ/4, subcarrier spacing 150 kHz; access point 400 m away. (pages 23)  
**Grade:** ❌ False 'not in the document'; the answer is on p.23

**Answer:**

> The document does not cover the carrier frequency, the RIS size, the number of elements, or the subcarrier spacing for the wideband simulation of Fig. 6.
>
> (The answer says the document does not cover this. Pages checked: p.4, p.6, p.7, p.18, p.23, p.28, p.36)

## RA5 — ❌

**File:** ris_tutorial.pdf  
**Question:** Fig. 6(a)에서 heuristic STM 구성은 상한의 몇 %를 달성하고, NLOS인 Fig. 6(b)에서는 어떻게 돼?  
**Expected:** 96-98% of the upper bound (46) with LOS to the RIS; with an NLOS path to the RIS the gain collapses (vanishes as B increases). (pages 23, 24)  
**Grade:** ❌ Says the percentage is not given; the NLOS part (4% in the narrowband case) is right

**Answer:**

> 문서는 Fig. 6(a)에서 heuristic STM 구성이 상한의 몇 %를 달성하는지에 대한 구체적인 수치를 제공하지 않습니다. 그러나 Fig. 6(b)의 경우, NLOS 경로가 있는 경우 RIS가 4%의 향상을 보인다고 언급하고 있습니다 [p.23].
>
> 출처: p.23 (To evaluate the quality of the heuristic STM solut)

## RA6 — ⚠️

**File:** ris_tutorial.pdf  
**Question:** Doppler cloaking이 뭐고 어디에 쓸 수 있어?  
**Expected:** Each element tunes its delay to counteract the change of the RIS-to-receiver delay, so the Doppler effect is not observable; radar/sonar noise reduction, invisibility cloaks, legacy systems at high mobility, IoT devices to fast satellites. (pages 20)  
**Grade:** ⚠️ Content right, but expands RIS as 'Reflective Intelligent Surface', a name the paper never uses

**Answer:**

> Doppler cloaking은 RIS(Reflective Intelligent Surface)가 지연을 조정하여 Doppler 효과를 완화하는 기술로, RIS가 τθn(t)를 구현하여 τn,b(t)의 변화율을 상쇄하는 방식으로 작동합니다. 이는 Doppler 효과가 수신 신호에서 관측되지 않도록 만드는 기술입니다 [p.20].
>
> Doppler cloaking은 다양한 분야에서 활용될 수 있습니다. 예를 들어, 이 기술은 이동하는 물체가 레이더 및 소나 시스템에 의해 생성하는 전자기 노이즈를 줄이기 위해 조사되었으며, 이동하는 물체에 대한 "불가시성 코트"를 만들기 위해 사용될 수 있습니다 [p.20]. 또한, Doppler cloaking은 고이동성 환경에서 설계되지 않은 기존 시스템을 배치하거나, 매우 간단한 수신기 사슬을 가진 IoT 장치를 우주에서 빠르게 움직이는 위성과 연결하는 데 사용될 수 있습니다 [p.20].
>
> 출처: p.20 (Transmitter)

## RA7 — ❌

**File:** ris_tutorial.pdf  
**Question:** Because the RIS is passive, where must channel estimation be carried out, and what is it sufficient to estimate?  
**Expected:** At the receiver; it is sufficient to estimate the matrix V, the cascade of the transmitter-RIS and RIS-receiver channels. (pages 24)  
**Grade:** ❌ 'At the receiver' right but cited to p.7; 'sufficient to estimate h(t)' is wrong (the paper: the cascade matrix V, p.24)

**Answer:**

> Because the RIS is passive, channel estimation must be carried out at the receiver [p.7]. It is sufficient to estimate the end-to-end channel $ h(t) $ [p.7].
>
> Sources: p.7 (an external stimulus represented by the variable θ)

## RA8 — ✅

**File:** ris_tutorial.pdf  
**Question:** Fig. 7에서 4G, 5G, beyond 5G의 측위 방식은 각각 어떤 측정을 써?  
**Expected:** 4G: TDOA from multiple BSs; 5G: TDOA + AOA + AOD; beyond 5G: TDOA + AOD with a single BS and an RIS. (pages 27)  
**Grade:** ✅ Correct

**Answer:**

> Fig. 7에서 4G의 측위 방식은 TDOA (Time Difference of Arrival) 측정을 사용한다 [p.26].  
> 5G의 측위 방식은 TDOA (Time Difference of Arrival), AOA (Angle of Arrival), AOD (Angle of Departure) 측정을 사용한다 [p.26].  
> Beyond 5G의 측위 방식은 TDOA (Time Difference of Arrival)와 AOD (Angle of Departure) 측정을 사용한다 [p.27].
>
> 출처: p.26 (frequency shifts) from received signals. Note that), p.27 (4G: TDOA 5G: TDOA+AOA+AOD Beyond 5G: TDOA+AOD)

## RA9 — ✅

**File:** ris_tutorial.pdf  
**Question:** 4G에서 3차원 위치를 구하려면 최소 몇 개 기지국의 TOA가 필요하고, 다중경로 때문에 정확도는 어느 정도로 제한돼?  
**Expected:** TOAs from at least four BSs in LOS give three TDOAs for the 3D location; multipath limits the accuracy to tens of meters. (pages 26)  
**Grade:** ✅ Correct

**Answer:**

> 4G에서 3차원 위치를 구하려면 최소 4개 기지국의 TOA가 필요하다 [p.26]. 다중경로 때문에 정확도는 수십 미터로 제한된다 [p.26].
>
> 출처: p.26 (frequency shifts) from received signals. Note that)

## RA10 — ✅

**File:** ris_tutorial.pdf  
**Question:** What are the two types of control channel for configuring an RIS, and how do they differ?  
**Expected:** Out-of-band does not consume the useful bandwidth (wired or other spectrum); in-band consumes part of it, and can even be sent with the payload, which makes the end-to-end channel no longer AWGN. (pages 13)  
**Grade:** ✅ Correct

**Answer:**

> There are two types of control channels for configuring an RIS: out-of-band and in-band. An out-of-band control channel does not consume part of the useful bandwidth $ B $ and is implemented as a wired link or a wireless channel that uses a different frequency spectrum [p.13]. In contrast, an in-band control channel consumes part of the useful bandwidth to configure the RIS, and this should be factored in when computing the overall capacity of the wireless channel [p.13].
>
> Sources: p.13 (If any of the above assumptions are violated (e.g.)

## RA11 — ✅

**File:** ris_tutorial.pdf  
**Question:** Write the SNR upper bound of equation (31) in LaTeX.  
**Expected:** SNR <= P/(B N0) | sqrt(rho) + sum_{n=1}^N sqrt(alpha_n beta_n gamma) |^2. (pages 16)  
**Grade:** ✅ Correct; the warning that p.16 was not read is accurate

**Answer:**

> The SNR upper bound of equation (31) is given by:
>
> $$
> \text{SNR} \leq \frac{P}{BN_0} \left( \sqrt{\rho} + \sum_{n=1}^{N} \sqrt{\alpha_n \beta_n \gamma} \right)^2
> $$
>
> This expression is derived using the Cauchy-Schwartz inequality [p.16].
>
> Sources: p.16 (Conventional)
>
> ⚠ The equations in this answer were written without reading the original page (p.16). Check them against the document.

## RA12 — ⚠️

**File:** ris_tutorial.pdf  
**Question:** 이 논문으로 시험 문제 3개를 만들어 줘. 답과 출처도 같이.  
**Expected:** Three questions whose answers match the paper, each with a correct page citation.  
**Grade:** ⚠️ 929 s (26 parts); PEB expanded as 'Predicted Error Bound' (it is the position error bound)

**Answer:**

> 다음은 주어진 논문 내용을 바탕으로 만든 시험 문제 3개입니다. 각 문제는 출처 페이지와 함께 제공됩니다.
>
> ---
>
> ### **문제 1: RIS의 위치 배치와 PEB의 관계**
>
> **질문:**  
> RIS가 왼쪽 벽에 설치된 경우, PEB(Predicted Error Bound)의 분포는 어떻게 되는가? 이에 따라 RIS의 위치 배치가 위치 추정 성능에 미치는 영향을 설명하시오.
>
> **정답:**  
> RIS가 왼쪽 벽에 설치된 경우, RIS 근처에서만 낮은 PEB를 얻을 수 있으며, BS와 RIS 사이의 선 뒤에서는 PEB가 무한대에 가까워진다. 이는 RIS의 위치가 사용자와의 거리에 따라 PEB에 큰 영향을 미친다는 것을 보여준다. 따라서 RIS를 여러 위치에 배치함으로써 배치 지역 전역에서 균일한 커버리지를 제공할 수 있다.
>
> **출처:**  
> [p.35]
>
> ---
>
> ### **문제 2: RIS의 SNR 증가 비율과 요소 수의 관계**
>
> **질문:**  
> RIS의 SNR 증가 비율은 어떻게 표현되며, 이 비율이 RIS 요소 수(N)에 따라 어떻게 변화하는가? 또한, 이 비율이 통신과 위치 추적에서 다른 의미를 갖는 이유를 설명하시오.
>
> **정답:**  
> RIS의 SNR 증가 비율은 (Nαγ) · (Nβ)로 분해할 수 있으며, 첫 번째 항은 RIS가 반사하는 송신기 신호 전력 비율을 나타내며, 두 번째 항은 RIS 요소 수에 따른 영향을 나타낸다. 통신에서는 많은 RIS 요소가 필요하지만, 위치 추적에서는 대역폭이 필요하고 RIS는 작을 수 있다. 이는 통신에서는 LOS 경로가 존재할 경우 RIS의 이득이 제한적이지만, 위치 추적에서는 두 경로 모두 유용한 정보를 제공하기 때문이다.
>
> **출처:**  
> [p.36]
>
> ---
>
> ### **문제 3: RIS의 상호 결합과 그 영향**
>
> **질문:**  
> RIS 요소가 밀집 배치될 경우 발생하는 현상은 무엇인가? 이 현상이 알고리즘 설계 및 통신/위치 추적 성능에 미치는 영향을 설명하시오.
>
> **정답:**  
> RIS 요소가 밀집 배치될 경우, 상호 결합(mutual coupling)이 발생하여 하나의 요소의 임피던스가 이웃 요소의 임피던스와 연결된다. 이는 RIS 요소의 주파수 응답에 이웃 요소의 구성에 따라 영향을 미친다. 상호 결합은 알고리즘 설계 및 통신/위치 추적 성능에 영향을 미치며, 정확한 모델 개발이 어려울 경우 머신러닝 방법이 시스템 식별에 유용할 수 있다.
>
> **출처:**  
> [p.38]
>
> ---
>
> 필요하시면 추가 문제도 만들어 드릴 수 있습니다.
>
> 출처: p.35 (better to put the RIS on the wall facing the RIS (), p.36 (the TOA of the uncontrollable channel, we obtain a), p.38 (before it is reradiated [46]. This effectively cre)

## RH1 — pass

**File:** ris_tutorial.pdf  
**Question:** 논문에 나온 RIS 하드웨어 프로토타입의 제작 비용은 얼마야?  
**Expected:** No prototype cost is given.  
**Grade:** pass Not in the document

**Answer:**

> 논문에 RIS 하드웨어 프로토타입의 제작 비용에 대한 정보는 포함되어 있지 않다.
>
> (문서에 없다는 답입니다. 확인한 페이지: p.4, p.17, p.23, p.29, p.34, p.40)
