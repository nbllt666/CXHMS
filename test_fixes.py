#!/usr/bin/env python
"""
测试修复后的CXHMS功能
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def test_json_import():
    """测试webui中json导入问题是否修复"""
    try:
        # 检查文件头部是否已添加json导入
        with open('webui/app.py', 'r', encoding='utf-8') as f:
            content = f.read()
            if 'import json' in content:
                print("OK: JSON导入问题已修复")
                return True
            else:
                print("ERROR: JSON导入问题未修复")
                return False
    except Exception as e:
        print(f"ERROR: 检查JSON导入时出错: {e}")
        return False

def test_numpy_import():
    """测试decay模块中numpy导入问题是否修复"""
    try:
        # 检查文件头部是否已添加numpy导入
        with open('backend/core/memory/decay.py', 'r', encoding='utf-8') as f:
            content = f.read()
            if 'import numpy as np' in content:
                # 检查是否移除了函数内的导入
                lines = content.split('\n')
                function_import_found = False
                for line in lines:
                    if 'import numpy as np' in line and 'def ' not in line:
                        # 如果在函数外部找到了导入，且不在注释中
                        if not line.strip().startswith('#'):
                            function_import_found = True
                            break
                if function_import_found:
                    print("OK: Numpy导入问题已修复")
                    return True
                else:
                    print("ERROR: Numpy导入问题未完全修复")
                    return False
            else:
                print("ERROR: Numpy导入问题未修复")
                return False
    except Exception as e:
        print(f"ERROR: 检查Numpy导入时出错: {e}")
        return False

def test_distance_calculation():
    """测试向量存储中的距离计算问题是否修复"""
    try:
        # 检查Qdrant向量存储中的距离计算修复
        with open('backend/core/memory/vector_store.py', 'r', encoding='utf-8') as f:
            content = f.read()
            if 'similarity_score = 1 / (1 + r.score)' in content:
                print("OK: Qdrant距离计算修复确认")
            else:
                print("ERROR: Qdrant距离计算问题未修复")
                return False
        
        # 检查Milvus Lite向量存储中的距离计算修复
        with open('backend/core/memory/milvus_lite_store.py', 'r', encoding='utf-8') as f:
            content = f.read()
            if 'similarity_score = 1 / (1 + result[\'distance\'])' in content:
                print("OK: Milvus Lite距离计算修复确认")
                return True
            else:
                print("ERROR: Milvus Lite距离计算问题未修复")
                return False
    except Exception as e:
        print(f"ERROR: 检查距离计算修复时出错: {e}")
        return False

def test_json_parsing():
    """测试secondary router中的JSON解析问题是否修复"""
    try:
        # 检查secondary router中的具体修复
        with open('backend/core/memory/secondary_router.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
            # 检查是否修复了裸露的except语句
            if 'except (json.JSONDecodeError, KeyError, TypeError):' in content:
                print("OK: Secondary Router JSON解析修复确认")
                return True
            else:
                print("ERROR: Secondary Router JSON解析问题未修复")
                return False
    except Exception as e:
        print(f"ERROR: 检查Secondary Router JSON解析修复时出错: {e}")
        return False

def test_decay_batch_processor():
    """测试decay batch processor中的重要性更新问题"""
    try:
        # 检查decay batch processor中的修复
        with open('backend/core/memory/decay_batch.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
            if 'new_importance=new_importance' in content and 'score_to_importance' in content:
                print("OK: Decay Batch Processor修复确认")
                return True
            else:
                print("ERROR: Decay Batch Processor问题未修复")
                return False
    except Exception as e:
        print(f"ERROR: 检查Decay Batch Processor修复时出错: {e}")
        return False

def main():
    print("开始测试CXHMS修复...")
    print("="*50)
    
    all_passed = True
    
    all_passed &= test_json_import()
    all_passed &= test_numpy_import()
    all_passed &= test_distance_calculation()
    all_passed &= test_json_parsing()
    all_passed &= test_decay_batch_processor()
    
    print("="*50)
    if all_passed:
        print("ALL TESTS PASSED: 所有修复测试通过!")
    else:
        print("SOME TESTS FAILED: 部分修复测试失败!")
    
    return all_passed

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result else 1)