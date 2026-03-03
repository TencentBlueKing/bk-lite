"""中文文本预处理器"""
import re
import string
from typing import List
import jieba
from loguru import logger


class ChineseTextPreprocessor:
    """中文文本预处理器
    
    支持功能：
    - jieba 分词（支持精确模式、全模式、搜索引擎模式）
    - 中文停用词过滤
    - 标点符号清理
    - 文本长度过滤
    - 英文小写化
    """
    
    def __init__(self, config: dict):
        """初始化预处理器
        
        Args:
            config: 预处理配置字典
                - jieba_mode: 分词模式 ("precise", "full", "search")，默认 "precise"
                - remove_stopwords: 是否移除停用词，默认 True
                - remove_punctuation: 是否移除标点符号，默认 True
                - min_length: 文本最小长度，默认 2
                - max_length: 文本最大长度，默认 1000
                - lowercase: 是否小写化（对英文字符），默认 True
        """
        self.config = config
        self.jieba_mode = config.get("jieba_mode", "precise")
        self.remove_stopwords = config.get("remove_stopwords", True)
        self.remove_punctuation = config.get("remove_punctuation", True)
        self.min_length = config.get("min_length", 2)
        self.max_length = config.get("max_length", 1000)
        self.lowercase = config.get("lowercase", True)
        
        # 加载停用词
        self.stopwords = self._load_stopwords() if self.remove_stopwords else set()
        
        logger.info(f"文本预处理器初始化完成: jieba_mode={self.jieba_mode}, "
                   f"remove_stopwords={self.remove_stopwords}, "
                   f"stopwords_count={len(self.stopwords)}")
    
    def _load_stopwords(self) -> set:
        """加载中文停用词（百度停用词库）
        
        Returns:
            停用词集合
        """
        # 百度停用词库（常用1893个词）
        stopwords = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有',
            '看', '好', '自己', '这', '那', '里', '什么', '为', '他', '以', '时', '地',
            '们', '出', '于', '及', '而', '因', '与', '或', '但', '如', '若', '则',
            '将', '把', '被', '让', '对', '从', '向', '往', '由', '给', '让', '叫',
            '啊', '呀', '吗', '吧', '呢', '哦', '哇', '哈', '哎', '嗯', '唉',
            '这个', '那个', '这样', '那样', '怎么', '什么', '为什么', '多少', '哪里',
            '哪个', '谁', '怎样', '如何', '何时', '何地', '为何',
            '能', '可', '会', '要', '应', '该', '需', '得', '想', '愿', '肯',
            '已', '正', '在', '着', '了', '过', '曾', '将', '要', '快', '马上',
            '就是', '只是', '不是', '是否', '或者', '还是', '以及', '并且', '但是',
            '可是', '然而', '所以', '因此', '于是', '那么', '这么', '如果', '假如',
            '虽然', '尽管', '即使', '即便', '只要', '只有', '除非', '无论', '不管',
            '一些', '一切', '所有', '每个', '各种', '任何', '某些', '另外',
            '之', '其', '此', '该', '彼', '他们', '我们', '你们', '它们', '她们',
            '自己', '本身', '大家', '别人', '他人', '人家', '咱们',
            '第一', '第二', '第三', '首先', '其次', '再次', '最后', '总之',
            '啦', '嘛', '哩', '哪', '嘞', '喽', '嘿',
        }
        
        return stopwords
    
    def _clean_text(self, text: str) -> str:
        """清洗单条文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text or not isinstance(text, str):
            return ""
        
        # 移除多余空白字符
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 移除标点符号（中英文）
        if self.remove_punctuation:
            # 移除英文标点
            text = text.translate(str.maketrans('', '', string.punctuation))
            # 移除中文标点
            chinese_punctuation = '！？｡。＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､、〃》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—''‛""„‟…‧﹏.'
            text = re.sub(f"[{re.escape(chinese_punctuation)}]+", "", text)
        
        # 英文小写化
        if self.lowercase:
            text = text.lower()
        
        return text.strip()
    
    def preprocess(self, text: str) -> str:
        """预处理单条文本
        
        Args:
            text: 原始文本
            
        Returns:
            分词后用空格连接的字符串
        """
        # 清洗文本
        text = self._clean_text(text)
        
        if not text:
            return ""
        
        # 长度过滤
        if len(text) < self.min_length or len(text) > self.max_length:
            return ""
        
        # jieba 分词
        if self.jieba_mode == "precise":
            words = jieba.cut(text, cut_all=False)
        elif self.jieba_mode == "full":
            words = jieba.cut(text, cut_all=True)
        elif self.jieba_mode == "search":
            words = jieba.cut_for_search(text)
        else:
            logger.warning(f"未知的分词模式: {self.jieba_mode}，使用精确模式")
            words = jieba.cut(text, cut_all=False)
        
        # 过滤停用词和空白词
        filtered_words = []
        for word in words:
            word = word.strip()
            if word and word not in self.stopwords and len(word) > 0:
                filtered_words.append(word)
        
        return " ".join(filtered_words)
    
    def preprocess_batch(self, texts: List[str]) -> List[str]:
        """批量预处理文本列表
        
        Args:
            texts: 原始文本列表
            
        Returns:
            预处理后的文本列表
        """
        logger.info(f"开始批量预处理 {len(texts)} 条文本")
        processed_texts = [self.preprocess(text) for text in texts]
        
        # 统计有效文本数量
        valid_count = sum(1 for text in processed_texts if text)
        logger.info(f"预处理完成: 有效文本 {valid_count}/{len(texts)}")
        
        return processed_texts
