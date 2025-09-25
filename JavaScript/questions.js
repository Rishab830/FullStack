function q1() {
    var num = prompt("Enter a number");
    if (num % 2 == 0){
        document.getElementById("1").innerText = "Even"
    }
    else{
        document.getElementById("1").innerText = "Odd"
    }
}

function q2(){
    var str = prompt("Enter a string to reverse");
    document.getElementById("2").innerText = str.split('').reverse().join('')
}

function q3(){
    var str = prompt("Enter a string to check for palindrome");
    var reverse_str = str.split('').reverse().join('')
    if (str == reverse_str){
        document.getElementById("3").innerText = "Yes, it is a palindrome"
    }
    else{
        document.getElementById("3").innerText = "No, it is not a palindrome"
    }
}

function q4(){
    var list_of_num = prompt('Enter comma seperated numbers').split(',').map(Number)
    console.log(typeof list_of_num)
    console.log(list_of_num)
    var max = 0
    for(var i=0;i<list_of_num.length;i++){{
        if(max < list_of_num[i]){
            max = list_of_num[i]
        }
    }
    }
    document.getElementById("4").innerText = max
}

function q5(){
    var list_of_num = prompt('Enter comma seperated numbers').split(',').map(Number)
    var sum = 0
    for(var i=0;i<list_of_num.length;i++){
        sum += list_of_num[i]
    }
    document.getElementById("5").innerText = sum
}

function q6(){
    var string = prompt('Enter string to be reversed')
    var reversed_string = ""
    for(var i=string.length-1;i>-1;i--){
        reversed_string += string[i]
    }
    document.getElementById("6").innerText = reversed_string
}
