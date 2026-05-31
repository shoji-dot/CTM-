with open('utils/mail.py', 'r', encoding='utf-8') as f:
    content = f.read()

# リンク形式を修正
old1 = 'smtp.gmail.com'
new1 = 'smtp.gmail.com'
old2 = 'msg.as_string()'
new2 = 'msg.as_string()'

content = content.replace(old1, new1)
content = content.replace(old2, new2)

with open('utils/mail.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('修正完了')
print(content[300:420])