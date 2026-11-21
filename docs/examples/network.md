# Network agent: answers from live runs

Questions asked to the agent on the MacBook, answered from what it measured at that moment (Wi-Fi link,
pings to the router and the internet, speed test, scan, Bluetooth). Copied from the run reports as given;
only the names of the home's networks and devices are replaced, and neighbours' networks left out.
The first block of each answer is the card built by code; the text after it is written by the local
model (qwen3:4b-instruct) from the same measurements, with every number checked against them.

## 게임 해도 돼?

Route: network · 35 s · case N10, run_20261121_130836

```text
지금 와이파이 · 신호 매우 좋음
핑: 평소 7 ms, 자주 튐 (8번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임 팁: AirDrop을 끄세요 (시스템 설정 → 일반 → AirDrop 및 연속성)
그래도 끊기면: 게임할 때만 이 연결을 꺼 두세요 → python scripts/game_watch.py --awdl off (끝나면 다시 켜져요)

게임을 하기는 가능하지만 주의해야 합니다. 공유기까지 지연 시간에 20ms 이상의 튐(36회)이 발생하고, 이는 AirDrop의 AWDL 기능이 활성화되어 발생한 것으로, 지터가 12.89ms이며 상위 5% 지연(p95)이 51.12ms로 높습니다. 게임 중 AirDrop을 끄고 AWDL을 비활성화하면 튐이 사라지며, 공유기까지 지연 시간이 평균 3.63ms로 안정화됩니다.
```

## 배그 핑 괜찮아?

Route: network · 35 s · case N13, run_20261121_130836

```text
지금 와이파이 · 신호 매우 좋음
핑: 평소 7 ms, 자주 튐 (8번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임 팁: AirDrop을 끄세요 (시스템 설정 → 일반 → AirDrop 및 연속성)
그래도 끊기면: 게임할 때만 이 연결을 꺼 두세요 → python scripts/game_watch.py --awdl off (끝나면 다시 켜져요)

배그 핑은 주의하면 가능합니다. 공유기까지 지연 시간의 핑 튐(20ms 이상)이 35회 발생하고, 이는 AirDrop 무선(AWDL)이 활성화되어 있어 발생합니다. 게임 중에는 AirDrop을 끄고 AWDL을 비활성화시켜야 하며, 공유기까지 지연 시간의 평균은 3.43ms로 유지됩니다.
```

## 여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어?

Route: network · 66 s · case N11, run_20261121_130836

```text
와이파이: Home-A-5G · 신호 매우 좋음 · 인터넷 속도 받기 279 / 보내기 157 Mb/s
핑: 평소 7 ms, 자주 튐 (9번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅   4K ✅   10 GB 받기 약 4.8분
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임하려면 "게임 해도 돼?"처럼 물어보세요. 바꿀 설정을 알려 드려요
추천: 지금 와이파이가 여기서 제일 좋아요
(비밀번호가 저장 안 된 와이파이는 비교에서 빠져요: Home-A-2.4G)

5GHz 채널 44에서 'Home-A-5G' 네트워크를 사용하고 있습니다. 신호 세기 -44.6 dBm, 신호 대 잡음비(SNR) 49.4 dB, 링크 속도 433 Mb/s로 최고 수준이지만, AirDrop(AWDL)이 활성화되어 공유기까지 지연 시간이 36회 이상 20ms 이상 튐(36 rises of 20 ms or more) 발생하고 있습니다. 게임이나 실시간 통신을 할 때는 AirDrop을 꺼야 하며, 공유기까지 지연 시간이 3.5ms에서 62.48ms로 급격히 오르는 현상이 발생하므로, 게임 중에는 AirDrop을 끄고, 게임 후에 다시 켜야 합니다.
```

## 와이파이로 뭐 할 수 있어? 자세히

Route: network · 63 s · case N14, run_20261121_130836

```text
지금: Home-A-5G, 신호 -45 dBm → SNR 49 dB → 256-QAM 5/6 (MCS 9) → 링크 433 Mb/s
측정: 다운 215 / 업 163 Mb/s, 평소 핑 7 ms, 스파이크 34회(와이파이 구간), 늦게 온 핑 11%, 손실 0%
게임 ⚠️ (와이파이 구간에서 튐)   화상회의 ✅   메신저 ✅   4K ✅   10 GB 다운 약 6.2분
핑이 튀는 원인: AirDrop 무선(AWDL). 게임하려면 "게임 해도 돼?"라고 물어보면 바꿀 설정을 알려 줌
병목: 와이파이 구간 (공유기까지 구간에서 이미 핑이 튐)
다른 와이파이:
  Home-C-5G (5 GHz ch 149): -75 dBm, SINR 19 dB, 예상 16-QAM 1/2, 링크 약 167 Mb/s (이 맥에 저장 안 됨)
  Home-A-2.4G (2.4 GHz ch 11): -44 dBm, SINR 53 dB, 예상 64-QAM 5/6, 링크 약 150 Mb/s (이 맥에 저장 안 됨)
  Home-C-2.4G (2.4 GHz ch 2): -68 dBm, SINR 29 dB, 예상 64-QAM 5/6, 링크 약 150 Mb/s
  Home-B-2.4G (2.4 GHz ch 11): -81 dBm, SINR 16 dB, 예상 QPSK 1/2, 링크 약 39 Mb/s (이 맥에 저장 안 됨)
  (저장 안 된 와이파이는 추천에서 빠짐: 한 번 연결해 비밀번호를 저장하면 비교에 들어감)
→ 지금 와이파이 유지

와이파이로는 브라우징, 메시징, 비디오 통화, 4K 스트리밍, 대용량 다운로드 및 업로드까지 모두 가능합니다. 그러나 공유기까지 지연 시간이 20ms 이상 튐이 발생하고, AirDrop(AWDL)이 활성화되어 있어 지연이 심화되는 문제가 있습니다. 게임이나 통화를 할 때는 AirDrop을 끄고, 부하가 생길 경우 대용량 다운로드를 일시 중단해야 합니다. 공유기까지 지연 시간은 3.4ms(평균), 상위 5% 지연은 48.03ms입니다.
```

## 화상 통화 해도 괜찮을까?

Route: network · 54 s · case N04, run_20261121_130836 · 'Video call' is also a kind of work for the performance agent; without battery words a call goes to the network agent.

```text
지금 와이파이 · 신호 매우 좋음 · 인터넷 속도 받기 241 / 보내기 162 Mb/s
핑: 평소 7 ms, 자주 튐 (7번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅   4K ✅   10 GB 받기 약 5.5분
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임하려면 "게임 해도 돼?"처럼 물어보세요. 바꿀 설정을 알려 드려요

화상 통화는 가능합니다. 공유기까지 지연 시간의 상위 5% 지연(p95)이 67.18ms이며, 지터가 15.55ms로 패킷 손실이 없고, 링크 속도가 433Mb/s이므로 연결 상태는 좋습니다. 그러나 AirDrop이 활성화되어 있어 공유기까지 지연이 뜨거지며, 이 경우 화상 통화 중 지연이 증가할 수 있으므로 AirDrop을 꺼야 합니다. 화상 통화를 하기 전에 AirDrop을 꺼주시고, 공유기까지 지연 시간이 3.48ms 이상 유지되도록 하세요.
```

## 인터넷 속도 어때? 4K 스트리밍 돼?

Route: network · 29 s · case N05, run_20261121_130836

```text
지금 와이파이 · 신호 매우 좋음 · 인터넷 속도 받기 226 / 보내기 160 Mb/s
핑: 평소 11 ms, 자주 튐 (7번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅   4K ✅   10 GB 받기 약 5.9분
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임하려면 "게임 해도 돼?"처럼 물어보세요. 바꿀 설정을 알려 드려요

인터넷 속도는 충분하며 4K 스트리밍은 가능합니다. 공유기까지 지연 시간이 8%에서 50ms 이상 튐이 발생하고, AirDrop의 무선 기능(AWDL)이 활성화되어 이에 기여하고 있습니다. AirDrop을 끄거나 게임 중에는 AWDL을 끄는 것이 필요합니다.
```

## Is my internet connection good enough for a video call?

Route: network · 44 s · case N09, run_20261121_130836

```text
Current Wi-Fi · signal excellent · speed 142 down / 202 up Mb/s
Ping: usually 7 ms, often jumps (1 in 7 late)
Games ⚠️ may stutter   Calls ✅   Messaging ✅   4K ✅   10 GB in about 9.4 min
Why it jumps: the Mac briefly leaves the Wi-Fi to talk to nearby Apple devices (your iPhone)
Ask about a game to get the settings to change

Yes, your internet connection is good enough for a video call. The latency to the internet is 6.69 ms (median), jitter is 16.65 ms, and there is no packet loss, which supports stable video calling. However, AirDrop is active and causes intermittent latency spikes (up to 68.65 ms at p95), so turning it off before a call will improve stability.
```

## 와이파이 왜 이렇게 느려?

Route: network · 14 s · case N01, run_20261121_130836

```text
지금 와이파이 · 신호 매우 좋음
핑: 평소 7 ms, 자주 튐 (8번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임하려면 "게임 해도 돼?"처럼 물어보세요. 바꿀 설정을 알려 드려요

와이파이가 느려지는 주된 원인은 공유기까지 지연 시간의 급격한 튐(20ms 이상)과 지터(17.6ms)가 발생하며, 이는 AirDrop의 무선 기능(AWDL)이 활성화되어 발생합니다. AWDL이 활성화되면 공유기까지 지연 시간의 상위 5% 지연(p95)이 68.6ms로 증가하고, 8%의 응답이 50ms 이상으로 높아집니다. 게임이나 통화 시 AirDrop을 끄고, 시스템 설정에서 'AirDrop & Handoff'를 통해 AWDL를 비활성화하세요.
```

## 핑 몇이야?

Route: network · 13 s · case N08, run_20261121_130836

```text
지금 와이파이 · 신호 매우 좋음
핑: 평소 7 ms, 자주 튐 (7번 중 1번은 늦게 옴)
게임 ⚠️ 가끔 끊길 수 있음   화상회의 ✅   메신저 ✅
핑이 튀는 이유: 맥이 근처 애플 기기(아이폰 등)와 연결하려고 와이파이를 잠깐씩 비워서 그래요
게임하려면 "게임 해도 돼?"처럼 물어보세요. 바꿀 설정을 알려 드려요

핑 몇이야? 공유기까지 지연 시간의 상위 5% 지연(p95)은 60.22ms이며, 이는 AWDL(airDrop 무선)이 활성화되어 핑 튐이 발생하는 것으로 판단됩니다. AWDL를 끄면 공유기까지 지연 시간의 p95가 약 3ms로 크게 개선됩니다. 게임을 할 때는 AWDL을 끄고, 시스템 설정에서 AirDrop 및 Handoff를 조정하세요.
```

## 블루투스 스피커 신호 괜찮아?

Route: network · 12 s · case N07, run_20261121_130836

```text
와이파이: 5 GHz · 신호 매우 좋음
블루투스: 켜짐
  연결됨: 없음
  연결 안 됨: Headset (헤드셋), Speaker (스피커), Mouse (마우스), iPhone (기기, 근처에 있음)
스피커: 페어링돼 있지만 지금 연결 안 됨 → 제어 센터 → 블루투스에서 선택하세요

블루투스 스피커 신호는 괜찮지 않습니다. 스피커(Speaker)는 페어링됨이지만 연결되어 있지 않습니다. 연결을 위해 Control Centre > Bluetooth에서 스피커를 선택하고, iPhone에 연결되어 있는지 확인해야 합니다.
```

## 에어팟 자꾸 끊겨

Route: network · 12 s · case N12, run_20261121_130836

```text
와이파이: 5 GHz · 신호 매우 좋음
블루투스: 켜짐
  연결됨: 없음
  연결 안 됨: Headset (헤드셋), Speaker (스피커), Mouse (마우스), iPhone (기기, 근처에 있음)
에어팟: 이 맥에 페어링돼 있지 않아요 → 아이폰에서 끊긴다면 아이폰과 에어팟 사이 문제예요

에어팟이 자꾸 끊기는 문제는 이 맥과 에어팟이 페어링되지 않았기 때문입니다. 현재 '에어팟'은 이 맥에 페어링됨이 없습니다. 에어팟을 사용하려면 iPhone과 함께 페어링된 후, 맥의 시스템 설정 > 블루투스에서 에어팟을 페어링해야 합니다.
```

## 게임 돌려도 돼?

Route: performance · 14 s · case N15, run_20261121_130836 · Running a game is the Mac's load, not the connection.

```text
게임을 돌릴 수 있습니다. 사용 가능한 메모리가 18.9GB로 게임이 요구하는 약 6GB를 충분히 초과하고 있으며, 현재 측정된 메모리 사용량도 충분히 확보되어 있습니다. 열 압력과 CPU, GPU 사용률은 정상이며, 전체 시스템의 성능 문제는 발견되지 않았습니다. 그러나 측정은 합성 작업에 기반했고, 실제로 게임을 실행할 때 더 높은 메모리와 전력 소비가 발생할 수 있습니다. 남은 저장 공간은 524.1GB로 충분하며, 저장 장치 건강도 확인되었습니다.
```
