# test_api_params.py
import requests
import argparse

def run_api_test(app_id: int):
    """
    用不同的参数组合测试 /appreviews API，并打印结果。
    """
    print(f"--- 正在为 AppID: {app_id} 测试不同的API参数 ---")
    
    base_url = f"https://store.steampowered.com/appreviews/{app_id}"

    # --- 定义我们要测试的4种参数组合 ---
    test_cases = {
        "1. Total Reviews (旧方法)": {
            "params": {'json': 1, 'filter': 'all', 'language': 'all'}
        },
        "2. Chinese Reviews (旧方法)": {
            "params": {'json': 1, 'filter': 'all', 'language': 'schinese'}
        },
        "3. Total Reviews (新方法: purchase_type=all)": {
            "params": {'json': 1, 'filter': 'all', 'purchase_type': 'all'}
        },
        "4. Chinese Reviews (新方法: purchase_type=all)": {
            "params": {'json': 1, 'filter': 'all', 'language': 'schinese', 'purchase_type': 'all'}
        }
    }

    # --- 依次执行每个测试 ---
    for name, case in test_cases.items():
        print(f"\n--- 正在执行测试: {name} ---")
        try:
            response = requests.get(base_url, params=case['params'], timeout=15)
            response.raise_for_status()
            data = response.json()

            if data and data.get('success') == 1:
                summary = data.get('query_summary', {})
                total_reviews = summary.get('total_reviews', 'N/A')
                print(f"✅ 成功！返回的 total_reviews: {total_reviews}")
            else:
                print(f"❌ 请求成功，但返回的数据无效。")

        except requests.exceptions.RequestException as e:
            print(f"❌ 请求失败: {e}")

    print("\n--- 测试结束 ---")
    print("请对比上面的结果和Steam商店页面的数字。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试 /appreviews API 的不同参数组合。")
    parser.add_argument("app_id", type=int, help="要测试的Steam游戏的AppID。")
    args = parser.parse_args()
    run_api_test(args.app_id)
