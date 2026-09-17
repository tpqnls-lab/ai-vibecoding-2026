"""2단부터 9단까지 출력하고, 선택한 단을 다시 보여 주는 구구단 프로그램."""


def print_multiplication_table(dan: int) -> None:
    """지정한 단의 구구단을 출력한다."""
    print(f"\n{dan}단")
    for number in range(1, 10):
        print(f"{dan} x {number} = {dan * number}")


def main() -> None:
    print("=== 구구단 2단 ~ 9단 ===")
    for dan in range(2, 10):
        print_multiplication_table(dan)

    while True:
        user_input = input("\n보고 싶은 단을 입력하세요 (2~9, 종료: q): ").strip()

        if user_input.lower() == "q":
            print("프로그램을 종료합니다.")
            break

        if not user_input.isdigit() or not 2 <= int(user_input) <= 9:
            print("2부터 9 사이의 숫자 또는 q를 입력하세요.")
            continue

        print_multiplication_table(int(user_input))


if __name__ == "__main__":
    main()
