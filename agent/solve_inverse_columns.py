import pandas as pd

df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})

inv_dict = {f"inv_{col}": 1/df[col] for col in df.columns}
result = df.assign(**inv_dict)

print("Original DataFrame:")
print(df)
print("\nResult DataFrame:")
print(result)