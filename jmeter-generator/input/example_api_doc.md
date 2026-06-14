# 示例接口文档

> 将您的接口文档放在此文件夹中，支持 Markdown / JSON / YAML / OpenAPI 格式。
> 一次性可以放多个文档，批量生成 JMeter 脚本。

## 接口1：用户登录

- **Method**: POST
- **URL**: https://api.example.com/login
- **Headers**:
  - Content-Type: application/json
- **Body**:
```json
{"username":"test_user","password":"pass123"}
```

## 接口2：获取用户信息

- **Method**: GET
- **URL**: https://api.example.com/user/profile
- **Headers**:
  - Authorization: Bearer ${token}

## 接口3：更新用户信息

- **Method**: PUT
- **URL**: https://api.example.com/user/profile
- **Headers**:
  - Content-Type: application/json
  - Authorization: Bearer ${token}
- **Body**:
```json
{"nickname":"new_nick","email":"test@example.com"}
```
