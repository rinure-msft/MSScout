# Speech model selection

Arthur uses balanced Zipformer INT8 through sherpa-onnx for activation and
short commands. It was the best fit for the project's Windows CPU testing:

| Measure | Balanced Zipformer INT8 |
| --- | ---: |
| Arthur wake recall | 8/9 |
| Word error rate | 20.6% |
| Real-time factor | 0.128 |
| Download size | About 189 MB |

Whisper medium.en was the strongest Whisper-only option tested, but it had
6/9 Arthur recall, 25.5% word error rate, a 1.53 GB download and took about
1.68 times the recording duration on CPU. It is not suitable as a continuous
wake detector.

Parakeet INT8 remains a possible post-activation option for future long-form
dictation experiments. It is not part of the production runtime.

These results are directional measurements from the project benchmark, not a
claim of universal accuracy. Raw voice clips and benchmark corpora are not
kept in the repository or release packages.
