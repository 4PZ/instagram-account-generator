import random
import string
import time

syl = "n,a,i,u,e,o,ka,ki,ku,ke,ko,ta,chi,tsu,te,to,sa,shi,su,se,so,na,ni,nu,ne,no,ha,hi,fu,he,ho,ma,mi,mu,me,mi,ya,yu,yo,ra,ri,ru,re,ro,wa,wo".split(",")
numbers = "0123456789"

def generate_syllabes(l):
    r = ""
    for i in range(l):
        r += random.choice(syl)
    return r

def generate_numbers(l):
    return ''.join(random.choices(numbers, k=l))

def generate_password(seed):
    random.seed(seed)
    final = ''.join(random.choices(string.ascii_lowercase, k=8))
    random.seed(seed+"_skudliq")
    final += generate_numbers(4)
    random.seed(time.time())
    return final

def generate_mail_BAD(max_length, numbers_count):
    n = 9999
    while n > max_length:
        words = generate_syllabes(max_length//2)
        numbers = generate_numbers(numbers_count)
        final = words+numbers
        n = len(final)
    return final

def generate_mail():
    words = generate_syllabes(7)
    if len(words) > 16:
        words = words[:-2]
    final = words
    while len(final) < 12:
        final += random.choice(numbers)
    return final + "@wilchan.org"

if __name__ == "__main__":
    mail = generate_mail()+"@wilchan.org"
    pwd = generate_password(mail)
    print("example mail: "+mail)
    print("example pwd: "+pwd)
