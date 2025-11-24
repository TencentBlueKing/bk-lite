from neco.mlops.classification.base_classification import BaseClassification
from sklearn.ensemble import RandomForestClassifier as SKLearnRandomForestClassifier


class RandomForestClassifier(BaseClassification):
    """随机森林分类器"""
    
    def build_model(self, train_params: dict):
        """构建随机森林模型"""
        default_params = {
            'n_estimators': 100,
            'max_depth': None,
            'min_samples_split': 2,
            'min_samples_leaf': 1,
            'max_features': 'sqrt',
            'random_state': 42,
            'n_jobs': -1
        }
        
        # 合并参数
        final_params = {**default_params, **train_params}
        
        return SKLearnRandomForestClassifier(**final_params)
    
    @staticmethod
    def get_default_search_space():
        """获取默认的超参数搜索空间"""
        return {
            'n_estimators': {'type': 'choice', 'choice': [50, 100, 200, 300]},
            'max_depth': {'type': 'choice', 'choice': [None, 5, 10, 20, 30]},
            'min_samples_split': {'type': 'choice', 'choice': [2, 5, 10]},
            'min_samples_leaf': {'type': 'choice', 'choice': [1, 2, 4]},
            'max_features': {'type': 'choice', 'choice': ['sqrt', 'log2', None]}
        }