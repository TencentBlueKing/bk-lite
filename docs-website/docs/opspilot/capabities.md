---
sidebar_position: 4
---

# 内置能力

汇总介绍 OpsPilot 中的各种内置能力，详细解析其作用。

## 模型

在这一块内容中，将详细介绍各个模型的类型、功能、应用场景等，帮助用户选用模型。

### LLM模型

#### HuggingFace系列

##### QwQ（阿里云通义千问推理模型）

- **核心功能**：通过强化学习提升数学、编程和逻辑推理能力，能用 “思考链” 逐步分析问题。
- **优势**：
  - 小而强：仅 320 亿参数（约 3.2 亿个 “知识节点”），性能却接近 6700 亿参数的 DeepSeek-R1 模型。
  - 多领域精通：数学题解答、代码生成、复杂逻辑推理（如合同条款分析）都能胜任。
- **作用**：
  - 数学推理：能解决复杂的数学问题，例如解答高难度的代数方程、几何证明题等。当你遇到一道复杂的数列推理题，它可以逐步分析推理过程，给出正确答案。
  - 编程辅助：帮助编写代码、调试代码以及对代码进行逻辑优化。如果你在编写一个 Python 程序时遇到逻辑错误，它可以帮你找出问题并提供解决方案。
  - 通用推理：处理各类需要逻辑思考的问题，如合同条款解读、逻辑谜题解答等。

#### DeepSeek 系列（国产高效模型）

##### DeepSeek-R1:1.5b

- **核心功能**：专注于代码领域的轻量级大语言模型，支持 Python、Java 等编程语言。
- **优势**：
  - 低配置运行：手机或普通电脑（8GB 内存）即可使用，不占资源。
  - 代码生成快：补全代码、生成函数、调试错误，速度比人工快 3-5 倍。
- **作用**：
  - 代码生成：根据需求快速生成各种编程语言的代码，如 Python、Java、C++ 等。如果你需要写一个简单的 Web 爬虫程序，它可以快速为你生成相应的 Python 代码。
  - 代码优化：对已有的代码进行优化，提高代码的运行效率和可读性。比如优化一个排序算法的代码，让它在处理大规模数据时速度更快。
  - 代码纠错：检查代码中的语法错误和逻辑错误，并给出修正建议。

#### OpenAI 系列（全球领先的通用模型）

##### 1. GPT-3.5-Turbo-16K

- **核心功能**：具有较长上下文处理能力的通用大语言模型，长文本处理（1.2 万字），性价比高。
- **优势**：
  - 多任务适配：写文章、翻译、数据分析、客服问答都能做。
  - 性价比高：在性能和成本之间取得了较好的平衡，相比于 GPT-4，使用成本更低，适合大多数企业和个人用户。
- **作用**：
  - 内容创作平台：在一些自媒体平台上，创作者可以利用它快速生成文章的大纲和初稿，提高创作效率。
  - 企业文档处理：企业在处理大量的文档时，如合同、报告等，可以使用它进行内容总结和关键信息提取。

##### 2. GPT-4-32K

- **核心功能**：具有超长上下文处理能力和强大多模态能力的顶级大语言模型。超长文本处理（2.4 万字），支持多模态（文本 + 图像）。
- **优势**：
  - 强大的综合能力：在语言理解、推理能力、创意生成等方面都表现出色，是目前最先进的大语言模型之一。
  - 多模态融合：打破了传统语言模型只能处理文本的限制，实现了文本和图像的融合交互，拓展了应用场景。
- **作用**：
  - 超长文本分析：能够处理长达 32K tokens 的文本，对超长篇幅的文档进行深入分析和理解，如对一部长篇小说进行情节分析和主题探讨。
  - 多模态交互：支持文本和图像的输入和输出，例如可以根据输入的图片生成相关的文字描述，或者根据文字描述生成图像。
  - 复杂问题解决：解决各种复杂的问题，包括高难度的数学问题、专业领域的技术问题等。

##### 3. GPT-4o（多模态全能模型）

- **核心功能**：旗舰级多模态模型，支持文本、音频、图像、视频的混合输入输出，主打 “全能交互” 能力。
- **优势**：
  - 速度与成本革新：处理速度提升 200%，价格降低 50%，速率限制提高 5 倍，兼顾高效与低成本。
  - 多模态能力突破：视觉上能精准识别图像视频细节，语音可直接交互且能识别情绪、模拟声音，还能实现跨模态融合创作。
  - 推理能力提升：在 0-shot COT MMLU 和传统的 5-shot no-CoT MMLU 评估中设定新高分，展现强大推理性能。
- **作用**：
  - 实时多模态推理：能同时对音频、视觉和文本进行实时推理，实现多模态信息的同步处理。
  - 跨语言翻译：可处理 50 种不同语言，满足全球不同语言人群间的交流翻译需求。
  - 复杂任务处理：具备强大的文本、推理和编码能力，能应对代码生成、数据分析等复杂工作。

#### LLM模型汇总

目前opspilot支持的大模型除了上述外，全量见下表

| 分类名称 | 模型图标 | 模型ID | 模型名称 | 模型类别 |
| --- | --- | --- | --- | --- |
| Baichuan（百川） | Baichuan | baichuan-2 | Baichuan 2 | 文本类 |
| Baichuan（百川） | Baichuan | baichuan-2-chat | Baichuan 2 Chat | 文本类 |
| CodeLlama | MetaAI | code-llama | CodeLlama | 代码类 |
| CodeLlama | MetaAI | code-llama-instruct | CodeLlama Instruct | 代码类 |
| CodeLlama | MetaAI | code-llama-python | CodeLlama Python | 代码类 |
| CodeGeeX | CodeGeeX | codegeex4 | CodeGeeX4 | 代码类 |
| CodeQwen | Alibaba | codeqwen1.5 | CodeQwen1.5 | 代码类 |
| CodeQwen | Alibaba | codeqwen1.5-chat | CodeQwen1.5 Chat | 代码类 |
| CodeShell |  | codeshell | CodeShell | 代码类 |
| CodeShell |  | codeshell-chat | CodeShell Chat | 代码类 |
| Codestral | Mistral | codestral-v0.1 | Codestral v0.1 | 代码类 |
| CogAgent | Zhipu | cogagent | CogAgent | 推理增强 |
| DeepSeek | DeepSeek | deepseek | DeepSeek | 推理增强 |
| DeepSeek | DeepSeek | deepseek-chat | DeepSeek Chat | 推理增强 |
| DeepSeek | DeepSeek | deepseek-coder | DeepSeek Coder | 代码类 |
| DeepSeek | DeepSeek | deepseek-coder-instruct | DeepSeek Coder Instruct | 代码类 |
| DeepSeek | DeepSeek | deepseek-prover-v2 | DeepSeek Prover v2 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1 | DeepSeek R1 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-0528 | DeepSeek R1 0528 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-0528-qwen3 | DeepSeek R1 0528 Qwen3 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-distill-llama | DeepSeek R1 Distill Llama | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-distill-qwen | DeepSeek R1 Distill Qwen | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2-chat | DeepSeek V2 Chat | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2-chat-0628 | DeepSeek V2 Chat 0628 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2.5 | DeepSeek V2.5 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v3 | DeepSeek V3 | 推理增强 |
| DeepSeek | DeepSeek |deepseek-v3-0324 | DeepSeek V3 0324 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-vl2 | DeepSeek VL2 | 多模态 |
| DianJin |  | DianJin-R1 | DianJin R1 | 推理增强 |
| ERNIE | Baidu | Ernie4.5 | ERNIE 4.5 | 文本类 |
| FinLLM |  | fin-r1 | Fin R1 | 推理增强 |
| Gemma | Gemma | gemma-3-1b-it | Gemma 3 1B IT | 文本类 |
| Gemma | Gemma | gemma-3-it | Gemma 3 IT | 文本类 |
| GLM（智谱） | ChatGLM | glm-4.1v-thinking | GLM 4.1V Thinking | 推理增强 |
| GLM（智谱） | ChatGLM | glm-4.5 | GLM 4.5 | 文本类 |
| GLM（智谱） | ChatGLM | glm-4v | GLM 4V | 文本类 |
| GLM（智谱） | ChatGLM | glm-edge-chat | GLM Edge Chat | 文本类 |
| GLM（智谱） | ChatGLM | glm4-0414 | GLM4 0414 | 文本类 |
| GLM（智谱） | ChatGLM | glm4-chat | GLM4 Chat | 文本类 |
| GLM（智谱） | ChatGLM | glm4-chat-1m | GLM4 Chat 1M | 文本类 |
| Gorilla |  | gorilla-openfunctions-v2 | Gorilla OpenFunctions v2 | 推理增强 |
| OpenAI | GPT | gpt-2 | GPT-2 | 文本类 |
| HuatuoGPT |  | HuatuoGPT-o1-LLaMA-3.1 | HuatuoGPT o1 LLaMA 3.1 | 文本类 |
| HuatuoGPT |  | HuatuoGPT-o1-Qwen2.5 | HuatuoGPT o1 Qwen2.5 | 文本类 |
| InternLM | Intern | internlm3-instruct | InternLM3 Instruct | 文本类 |
| InternVL |  | InternVL3 | InternVL3 | 文本类 |
| LLaMA | Meta | llama-2 | LLaMA 2 | 文本类 |
| LLaMA | Meta | llama-2-chat | LLaMA 2 Chat | 文本类 |
| LLaMA | Meta | llama-3 | LLaMA 3 | 文本类 |
| LLaMA | Meta | llama-3-instruct | LLaMA 3 Instruct | 文本类 |
| LLaMA | Meta | llama-3.1 | LLaMA 3.1 | 文本类 |
| LLaMA | Meta | llama-3.1-instruct | LLaMA 3.1 Instruct | 文本类 |
| LLaMA | Meta | llama-3.2-vision | LLaMA 3.2 Vision | 多模态 |
| LLaMA | Meta | llama-3.2-vision-instruct | LLaMA 3.2 Vision Instruct | 多模态 |
| LLaMA | Meta | llama-3.3-instruct | LLaMA 3.3 Instruct | 文本类 |
| Marco |  | marco-o1 | Marco o1 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-bf16 | MiniCPM 2B DPO BF16 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-fp16 | MiniCPM 2B DPO FP16 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-fp32 | MiniCPM 2B DPO FP32 | 文本类 |
| MiniCPM |  | minicpm-2b-sft-bf16 | MiniCPM 2B SFT BF16 | 文本类 |
| MiniCPM |  | minicpm-2b-sft-fp32 | MiniCPM 2B SFT FP32 | 文本类 |
| MiniCPM |  | MiniCPM-V-2.6 | MiniCPM V 2.6 | 文本类 |
| MiniCPM |  | minicpm3-4b | MiniCPM3 4B | 文本类 |
| MiniCPM |  | minicpm4 | MiniCPM4 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.1 | Mistral Instruct v0.1 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.2 | Mistral Instruct v0.2 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.3 | Mistral Instruct v0.3 | 文本类 |
| Mistral | Mistral | mistral-large-instruct | Mistral Large Instruct | 文本类 |
| Mistral | Mistral | mistral-nemo-instruct | Mistral NeMo Instruct | 文本类 |
| Mistral | Mistral | mistral-v0.1 | Mistral v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-8x22B-instruct-v0.1 | Mixtral 8x22B Instruct v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-instruct-v0.1 | Mixtral Instruct v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-v0.1 | Mixtral v0.1 | 文本类 |
| Moonlight |  | moonlight-16b-a3b-instruct | Moonlight 16B A3B Instruct | 文本类 |
| OpenHermes |  | openhermes-2.5 | OpenHermes 2.5 | 文本类 |
| OPT |  | opt | OPT | 文本类 |
| Orion |  | orion-chat | Orion Chat | 文本类 |
| Ovis |  | Ovis2 | Ovis2 | 文本类 |
| Phi |  | phi-2 | Phi-2 | 文本类 |
| Phi | | Phi-3 |Mini 128K Instruct | 文本类 |
| Phi |  | phi-3-mini-4k-instruct | Phi-3 Mini 4K Instruct | 文本类 |
| QvQ |  | QvQ-72B-Preview | QvQ 72B Preview | 文本类 |
| Qwen（千问） | Qwen | qwen-chat | Qwen Chat | 文本类 |
| Qwen（千问） | Qwen | qwen1.5-chat | Qwen1.5 Chat | 文本类 |
| Qwen（千问） | Qwen | qwen1.5-moe-chat | Qwen1.5 MoE Chat | 文本类 |
| Qwen（千问） | Qwen | qwen2-audio | Qwen2 Audio | 多模态 |
| Qwen（千问） | Qwen | qwen2-audio-instruct | Qwen2 Audio Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen2-instruct | Qwen2 Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2-moe-instruct | Qwen2 MoE Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2-vl-instruct | Qwen2 VL Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen2.5 | Qwen2.5 | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-coder | Qwen2.5 Coder | 代码类 |
| Qwen（千问） | Qwen | qwen2.5-coder-instruct | Qwen2.5 Coder Instruct | 代码类 |
| Qwen（千问） | Qwen | qwen2.5-instruct | Qwen2.5 Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-instruct-1m | Qwen2.5 Instruct 1M | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-omni | Qwen2.5 Omni | 多模态 |
| Qwen（千问） | Qwen | qwen2.5-vl-instruct | Qwen2.5 VL Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen3 | Qwen3 | 文本类 |
| Qwen（千问） | Qwen | Qwen3-Coder | Qwen3 Coder | 代码类 |
| Qwen（千问） | Qwen | Qwen3-Instruct | Qwen3 Instruct | 文本类 |
| Qwen（千问） | Qwen | Qwen3-Thinking | Qwen3 Thinking | 推理增强 |
| Qwen（千问） | Qwen | qwenLong-l1 | QwenLong L1 | 文本类 |
| QwQ |  | QwQ-32B | QwQ 32B | 文本类 |
| QwQ |  | QwQ-32B-Preview | QwQ 32B Preview | 文本类 |
| SEALLM |  | seallm_v2 | SEALLM v2 | 文本类 |
| SEALLM |  | seallm_v2.5 | SEALLM v2.5 | 文本类 |
| SEALLM |  | seallms-v3 | SEALLMS v3 | 文本类 |
| Skywork |  | Skywork | Skywork | 文本类 |
| Skywork |  | Skywork-Math | Skywork Math | 推理增强 |
| Skywork |  | skywork-or1 | Skywork OR1 | 推理增强 |
| Skywork |  | skywork-or1-preview | Skywork OR1 Preview | 推理增强 |
| Telechat |  | telechat | Telechat | 文本类 |
| TinyLlama |  | tiny-llama | Tiny Llama | 文本类 |
| WizardCoder |  | wizardcoder-python-v1.0 | WizardCoder Python v1.0 | 代码类 |
| WizardMath |  | wizardmath-v1.0 | WizardMath v1.0 | 推理增强 |
| XiYanSQL |  | XiYanSQL-QwenCoder-2504 | XiYanSQL QwenCoder 2504 | 代码类 |
| Xverse |  | xverse | Xverse | 文本类 |
| Xverse |  | xverse-chat | Xverse Chat | 文本类 |
| Yi（零一万物） | Yi | Yi | Yi | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5 | Yi 1.5 | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5-chat | Yi 1.5 Chat | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5-chat-16k | Yi 1.5 Chat 16k | 文本类 |
| Yi（零一万物） | Yi | Yi-200k | Yi 200k | 文本类 |
| Yi（零一万物） | Yi | Yi-chat | Yi Chat | 文本类 |

### Embed 模型

#### FastEmbed（bge-small-zh-v1.5）

核心功能

轻量化中文语义嵌入模型，专注于将中文文本转化为计算机可理解的“数字编码”，高效捕捉语义相似性。

优势

- **轻量快速**：仅 95MB 大小，普通电脑也能运行，处理速度毫秒级响应，适合实时场景。
- **中文专精**：深度优化中文语义，精准识别成语、网络用语、专业术语（如法律、医疗词汇），语义匹配更准确。
- **低成本易用**：开源免费，无需复杂配置，直接集成到搜索、推荐等系统中降低开发成本。

作用

- **文本语义转化**：将中文句子/段落转化为高维向量，让计算机“理解”文字含义（如区分“打折”和“促销”的语义相似性）。
- **高效语义检索**：在海量文本中快速定位语义匹配内容（如用户输入“天气太热怎么办”，找到相关解暑攻略）。
- **智能系统赋能**：为客服、推荐、文档管理等系统提供语义支持，提升信息处理精度。

#### BCEmbedding（bce-embedding-base_v1）

核心功能

中英双语语义桥梁模型，支持中文和英文文本的双向语义转化，打破跨语言理解壁垒。

优势

- **双语精准对齐**：基于有道翻译技术，中英语义向量高度匹配（如“人工智能”与“Artificial Intelligence”编码相近），跨语言检索准确率提升 40%。
- **长文本处理**：支持数万字文档（如合同、论文）的整体语义编码，避免碎片化信息丢失。
- **双阶段检索**：先快速筛选语义相关文本（缩小范围），再精准排序，提升复杂场景下的检索质量。

作用

- **跨语言语义映射**：将中文和英文文本转化为统一向量空间，实现双语语义“无缝对接”（如中文提问匹配英文文档）。
- **跨语言检索支持**：在中英混合文本库中，支持任意语言输入检索另一语言内容（如英文搜索找到中文产品说明）。
- **多语言系统增强**：为跨国企业、教育、电商等场景提供双语语义支持，优化跨语言信息处理效率。

#### 模型列表

| 品牌名 | 图标  模型ID| 模型名称 |
|------------------|----------|----------------------------------|------------------------------|
| 网易有道         |          | bce-embedding-base_v1           | BCE Embedding Base v1        | 可通过 ollama 部署：`ollama pull lrs33/bce-embedding-base_v1`           |
| BAAI (智源研究院) | BAAI     | bge-base-en                     | BGE Base English             |
| BAAI (智源研究院) | BAAI     | bge-base-en-v1.5                | BGE Base English v1.5        |
| BAAI (智源研究院) | BAAI     | bge-base-zh                     | BGE Base Chinese             |
| BAAI (智源研究院) | BAAI     | bge-base-zh-v1.5                | BGE Base Chinese v1.5        |
| BAAI (智源研究院) | BAAI     | bge-large-en                    | BGE Large English            |
| BAAI (智源研究院) | BAAI     | bge-large-en-v1.5               | BGE Large English v1.5       |
| BAAI (智源研究院) | BAAI     | bge-large-zh                    | BGE Large Chinese            |
| BAAI (智源研究院) | BAAI     | bge-large-zh-noinstruct         | BGE Large Chinese NoInstruct |
| BAAI (智源研究院) | BAAI     | bge-large-zh-v1.5               | BGE Large Chinese v1.5       |
| BAAI (智源研究院) | BAAI     | bge-m3                          | BGE M3                       |
| BAAI (智源研究院) | BAAI     | bge-small-en-v1.5               | BGE Small English v1.5       |
| BAAI (智源研究院) | BAAI     | bge-small-zh                    | BGE Small Chinese            |
| BAAI (智源研究院) | BAAI     | bge-small-zh-v1.5               | BGE Small Chinese v1.5       |
| 微软             |          | e5-large-v2                     | E5 Large v2                  |
| 阿里             | Alibaba  | gte-base                        | GTE Base                     |
| 阿里             | Alibaba  | gte-large                       | GTE Large                    |
| 阿里             | Alibaba  | gte-Qwen2                       | GTE Qwen2                    |
| Jina AI          | Jina     | jina-clip-v2                    | Jina CLIP v2                 |
| Jina AI          | Jina     | jina-embeddings-v2-base-en      | Jina Embeddings v2 Base EN   |
| Jina AI          | Jina     | jina-embeddings-v2-base-zh      | Jina Embeddings v2 Base ZH   |
| Jina AI          | Jina     | jina-embeddings-v2-small-en     | Jina Embeddings v2 Small EN  |
| Jina AI          | Jina     | jina-embeddings-v3              | Jina Embeddings v3           |
| Jina AI          | Jina     | jina-embeddings-v4              | Jina Embeddings v4           |
| Moka AI          |          | m3e-base                        | M3E Base                     |
| Moka AI          |          | m3e-large                       | M3E Large                    |ge                               |
| Moka AI          |          | m3e-small                       | M3E Small                    |
| 微软             |          | multilingual-e5-large           | Multilingual E5 Large        |
| 阿里             | Alibaba  | Qwen3-Embedding-0.6B            | Qwen3 Embedding 0.6B         |
| 阿里             | Alibaba  | Qwen3-Embedding-4B              | Qwen3 Embedding 4B           |
| 阿里             | Alibaba  | Qwen3-Embedding-8B              | Qwen3 Embedding 8B           |
| 赛博智能         |          | text2vec-base-chinese           | Text2Vec Base Chinese        |
| 赛博智能         |          | text2vec-base-chinese-paraphrase | Text2Vec Base Chinese Paraphrase |
| 赛博智能         |          | text2vec-base-chinese-sentence  | Text2Vec Base Chinese Sentence |
| 赛博智能         |          | text2vec-base-multilingual      | Text2Vec Base Multilingual   |
| 赛博智能         |          | text2vec-large-chinese          | Text2Vec Large Chinese       |

### Rerank 模型

#### BCEReranker（bce-reranker-base_v1）

核心功能

基于交叉编码器的中英日韩多语言重排序模型，专注于对初始检索结果进行精细化排序，提升信息检索的相关性和准确性。它与 BCEmbedding 模型形成"双阶段检索"组合，先通过 BCEmbedding 召回候选文档，再由 BCEReranker 对 Top 50-100 个结果进行重排，最终输出 Top 5-10 个高相关性片段。

优势

- **多语言跨域适配**：支持中文、英文、日文、韩文四语种，尤其在中英跨语言检索中表现突出（如中文查询匹配英文文档），适配教育、法律、金融、医疗等多领域数据。
- **长文本精准排序**：突破传统模型 512 Token 的输入限制，支持数万字文档的整体语义分析，有效处理合同、论文等长文本场景，避免碎片化信息干扰。
- **绝对分数过滤**：输出可量化的"绝对相关性分数"（推荐阈值 0.35-0.4），直接过滤低质量结果，减少 LLM 生成时的"幻觉"问题。
- **RAG 深度优化**：针对检索增强生成（RAG）场景设计，与 BCEmbedding 组合在 LlamaIndex 评测中达到 SOTA 水平，跨语言检索准确率提升 40%，MRR（平均倒数排名）提升 6.85%。

作用

- **检索结果精排**：对初始召回的文本片段进行二次排序，确保最相关内容优先展示（如用户搜索"人工智能发展趋势"，模型会优先展示最新政策文件而非过时资料）。
- **跨语言信息整合**：支持中英日韩混合检索，例如中文用户输入"气候变化应对措施"，模型可匹配英文国际协议、日文研究报告等多语言资源，实现跨语言知识融合。
- **长文档语义聚焦**：处理技术手册、法律条文等长文本时，精准定位与查询相关的段落（如搜索"合同违约责任"，直接跳转到对应条款而非全文检索），提升信息提取效率。
- **低质内容过滤**：通过绝对分数阈值（如 0.4）自动剔除不相关或低质量结果，减少 LLM 处理无效信息的耗时，优化整体响应速度。

---

#### rerank模型列表

| 品牌名  | 图标 | 模型| 模型名称 |
|------------------|----------|----------------------------------|------------------------------|
| 网易有道         |          | bce-reranker-base_v1            | BCE Reranker Base v1         |
| BAAI (智源研究院) | BAAI     | bge-reranker-base               | BGE Reranker Base            |
| BAAI (智源研究院) | BAAI     | bge-reranker-large              | BGE Reranker Large           |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-gemma           | BGE Reranker v2 Gemma        |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-m3              | BGE Reranker v2 M3           |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-minicpm-layerwise | BGE Reranker v2 MiniCPM Layerwise |
| Jina AI          | Jina     | jina-reranker-v2                | Jina Reranker v2             |
| OpenBMB          |          | minicpm-reranker                | MiniCPM Reranker             |
| 阿里             | Alibaba  | Qwen3-Reranker-0.6B             | Qwen3 Reranker 0.6B          |
| 阿里             | Alibaba  | Qwen3-Reranker-4B               | Qwen3 Reranker 4B            |
| 阿里             | Alibaba  | Qwen3-Reranker-8B               | Qwen3 Reranker 8B            |

---

### OCR 模型

#### OlmOCR

核心功能

基于大型语言模型的文档解析工具，专注于将 PDF、图像等非结构化文档转化为可编辑文本，支持表格、公式、手写内容的精准提取，尤其擅长处理复杂排版（如多栏布局、学术论文）。

优势

- **多模态融合**：结合语言模型（如 ChatGPT-4o、Qwen2-VL）与计算机视觉技术，通过上下文推理提升文本识别准确性，减少幻觉现象（如虚构内容）。
- **结构化输出**：保留文档原始格式（如表格、项目符号、边注），支持 Markdown 或 Dolma 格式输出，便于后续分析和编辑。
- **低成本高效**：开源工具包支持本地 GPU 部署，每处理 100 万页文档成本仅 190 美元，适合大规模文档数字化需求。

作用

- **学术与技术文档处理**：解析论文、技术手册中的公式、图表和多栏内容，生成结构化文本（如将 LaTeX 公式转换为可编辑格式）。
- **手写内容识别**：处理医疗记录、历史档案中的手写文字，准确率超 90%，支持 12 种语言的手写体识别。
- **PDF 数字化**：将扫描 PDF 转换为可搜索文本，保留原始排版，适用于法律合同、古籍修复等场景。

#### AzureOCR

核心功能

微软 Azure 云服务中的 OCR 工具，支持多语言文本识别（含手写和打印体），集成于表单识别器（Form Recognizer），可提取表格、发票、身份证等文档的结构化数据。

优势

- **云服务集成**：与 Azure AI 服务（如翻译、语言理解）无缝对接，支持 REST API 和低代码平台（如 Power Automate），快速部署至企业流程。
- **多语言与混合场景**：支持中文、英文、日文等 50+ 语言，可同时处理文档中的混合语言内容，适用于跨国企业的多语言数据管理。
- **高精度与安全**：基于深度学习模型，识别准确率高，且数据存储符合 ISO、GDPR 等合规标准，保障企业数据安全。

作用

- **表单自动化**：自动提取发票、报销单中的金额、日期等字段，减少人工录入错误（如将手写签名与打印文字分离识别）。
- **文档分析**：解析合同中的条款、身份证中的个人信息，生成结构化 JSON 数据，便于后续数据分析或 AI 模型训练。
- **实时处理**：支持实时视频流中的文本识别（如监控画面中的车牌、公告文字），适用于安防、物流等场景。

#### PaddleOCR

核心功能

百度开源的 OCR 工具包，提供端到端文本检测、识别和方向分类，支持 80+ 语言（含中文、日文、韩文），覆盖通用、金融、交通等多领域垂类模型。

优势

- **轻量与高效**：模型压缩技术（如 PP-OCRv4）将模型体积降至 8.5MB，移动端推理速度达毫秒级。
- **多语言与场景适配**：针对中文优化，支持复杂文本（如弯曲文字、低光照图像）。
- **开源与生态**：代码开源且文档完善，支持自定义训练和私有化部署。

作用

- **实时文本识别**：处理视频流或监控画面中的文字（如实时翻译路牌、提取视频字幕）。
- **文档管理**：批量处理扫描文档，提取关键信息（如合同中的甲方乙方、医疗报告中的诊断结果），提升办公效率。
- **跨语言支持**：实现中英日韩等多语言混合文本的识别与翻译，适用于跨境电商、教育等场景。

---

#### 模型汇总

| 模型      | 优势                                     | 作用                                   |
|-----------|------------------------------------------|----------------------------------------|
| OlmOCR    | 多模态融合，解析复杂排版（公式/手写），结构化输出 | 学术文档、手写档案、PDF 数字化处理       |
| AzureOCR  | 云服务集成，50+ 语言支持，安全合规           | 企业表单、合同解析，实时视频文本识别     |
| PaddleOCR | 轻量开源，80+ 语言（中文优化），端边云部署    | 移动端识别、批量文档处理、跨语言场景适配 |

---

## 工具

### 运维工具

#### Kubernetes Tools

介绍

Kubernetes 工具是一套针对 Kubernetes 集群的运维与管理工具，覆盖集群资源查询、状态监控、故障诊断及配置管理等功能，帮助用户高效管理容器化应用的部署、运行和维护。

作用

- **CI/CD 流程全链路管控**：
  - 任务可视化管理：通过列表清晰呈现 Jenkins 服务器上所有构建任务的名称、状态（启用/禁用）、最后构建时间及结果，便于团队快速定位异常任务（如连续失败的部署任务）。
  - 自动化触发与参数化构建：支持在触发构建时动态传入参数（如目标分支、环境变量、版本号），满足多环境（开发/测试/生产）差异化部署需求（例如：指定`--env=prod`触发生产环境构建）。

- **团队协作与流程审计**：
  - 构建任务追溯：通过任务列表快速查询历史构建记录，结合时间工具（如`get_current_time`）记录操作时间，形成完整的 CI/CD 审计日志（适用于金融、医疗等对合规性要求高的行业）。
  - 多工具集成支持：与代码仓库（Git）、制品仓库（Nexus）、监控系统（Prometheus）无缝对接，例如代码提交后自动触发 Jenkins 构建，构建完成后通过 Kubernetes 工具部署至集群，形成自动化流水线闭环。

- **故障恢复与应急处理**：
  - 批量任务操作：批量禁用过时任务或重新触发失败任务，避免手动逐个操作的低效性（如上线期间批量重启所有微服务构建任务）。
  - 灰度发布支持：通过分阶段触发构建任务，配合 Kubernetes 工具实现蓝绿部署或滚动更新，降低线上变更风险（如先触发测试环境构建，验证通过后触发生产环境构建）。

#### Jenkins

介绍

Jenkins 工具是一组用于与 Jenkins 持续集成/持续部署（CI/CD）平台交互的功能集合，提供对 Jenkins 服务器上构建任务的查询和操作能力，支持通过程序远程管理构建流程，实现自动化部署流程的控制与监控。

作用

- **集群资源精细化管理**：
  - 多维度资源查询：支持按命名空间（如`dev/test/prod`）或资源类型（Pod/Node/Service）筛选查询，满足复杂架构下的分层管理需求（例如：仅查看`prod`命名空间下的所有 Deployment 资源）。
  - 资源优化与清理：识别并清理孤立资源（如未被使用的 PVC、废弃的 Service），释放集群资源；通过节点容量分析（CPU/内存使用率），辅助集群扩缩容决策（如自动添加节点以应对流量高峰）。

- **全链路故障诊断与监控**：
  - 异常资源快速定位：通过筛选失败、Pending 或高重启次数的 Pod，结合事件日志（`list_kubernetes_events`），精准定位调度失败、依赖缺失、镜像拉取失败等问题（如某 Pod 因`image not found`持续失败，快速定位到镜像仓库权限问题）。
  - 日志与配置联动分析：导出异常资源的 YAML 配置，对比不同环境的配置差异（如生产环境缺少必要的环境变量），同时结合 Pod 日志（`get_kubernetes_pod_logs`）追踪代码运行时错误（如数据库连接字符串错误导致服务无法启动）。

- **自动化运维与标准化建设**：
  - 批量操作支持：基于资源列表（如 Pod/Node 列表）执行批量操作（如重启所有 Running 状态的 Pod、标记节点为不可调度），提升大规模集群管理效率。
  - 配置标准化管理：通过导出资源 YAML 实现配置版本控制（如将生产环境配置存档至 Git），确保多环境配置一致性；结合 CI/CD 工具实现配置变更的自动化校验和部署（如修改 Deployment YAML 后自动触发滚动更新）。

- **性能与稳定性保障**：
  - 节点健康监控：实时获取节点状态（Ready/NotReady）及资源使用率，配合监控系统（如 Grafana）设置预警规则（如节点内存使用率超过 80% 时触发报警）。
  - 容器运行时分析：通过高重启次数 Pod 分析，定位容器内部的内存泄漏、死锁等问题，结合日志优化应用代码或容器配置（如增加资源请求限制`resources.requests`）。

### 通用工具

#### General tools

##### get_current_time（获取当前时间）

- **作用**：实时获取系统当前时间（精确到秒/毫秒），返回时间戳或指定格式的时间字符串（如`YYYY-MM-DD HH:MM:SS`）。
- **使用场景**：
  - **日志记录**：在系统操作（如用户登录、数据修改、任务执行）时添加时间戳，便于后续审计和问题追溯（例如：记录 API 调用时间、数据库变更时间）。
  - **任务调度**：作为定时任务的触发依据（如"每天 23:00 执行数据备份"），或计算任务耗时（开始时间 - 结束时间）。
  - **报表生成**：在生成日报、周报时自动插入当前时间，确保文档时效性（如财务报表、运维报告）。

---

#### 搜索工具

##### duckduckgo_search

- **作用**：通过 DuckDuckGo 搜索引擎发起网络查询，返回包含标题、链接、摘要的结构化搜索结果（支持文本关键词、自然语言提问）。
- **使用场景**：
  - **信息检索**：快速获取公开数据（如实时新闻、天气、百科知识），或技术类内容（如开源框架文档、错误代码解决方案）。
  - **数据采集**：批量搜索行业报告、竞品信息（如"2024 年 AI 芯片市场分析"），辅助决策分析。
  