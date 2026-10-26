package ch.bbw.m450.tictactoe.players;

import static ch.bbw.m450.tictactoe.BoardFixtures.toBoard;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

class PerfectPlayerTest {

	@Test
	void playsImmediateWin() {
		var board = toBoard("XX.OO....");

		assertThat(new PerfectPlayer().play(board, Stone.CROSS)).isEqualTo(2);
	}

	@Test
	void blocksImmediateLoss() {
		var board = toBoard("OO.X..X..");

		assertThat(new PerfectPlayer().play(board, Stone.CROSS)).isEqualTo(2);
	}

	@ParameterizedTest
	@EnumSource(Stone.class)
	void neverLosesAgainstAnyLegalOpponentMoves(Stone perfectColor) {
		assertNeverLoses(new Stone[TicTacToeMain.BOARD_SIZE], Stone.CROSS, perfectColor);
	}

	@Test
	void twoPerfectPlayersDraw() {
		assertThat(TicTacToeMain.play(new PerfectPlayer(), new PerfectPlayer())).isNull();
	}

	@Test
	void cannotPlayOnFullBoard() {
		var board = toBoard("XOXXOOOXX");

		assertThatThrownBy(() -> new PerfectPlayer().play(board, Stone.CROSS))
				.isInstanceOf(IllegalStateException.class);
	}

	private static void assertNeverLoses(Stone[] board, Stone turn, Stone perfectColor) {
		if (Arrays.stream(board).noneMatch(stone -> stone == null)) {
			return;
		}
		if (turn == perfectColor) {
			var snapshot = board.clone();
			var move = new PerfectPlayer().play(board, turn);
			assertThat(board).as("player must not change the board").containsExactly(snapshot);
			assertThat(move).as("legal move").isBetween(0, board.length - 1);
			assertThat(board[move]).as("free square").isNull();
			board[move] = turn;
			if (!TicTacToeMain.isWin(board, turn)) {
				assertNeverLoses(board, turn.opponent(), perfectColor);
			}
			board[move] = null;
		} else {
			for (var move = 0; move < board.length; move++) {
				if (board[move] == null) {
					board[move] = turn;
					assertThat(Arrays.stream(Stone.values())
							.filter(color -> TicTacToeMain.isWin(board, color))
							.toList())
							.as("opponent must never win with move %s on %s", move, Arrays.toString(board))
							.doesNotContain(turn);
					assertNeverLoses(board, perfectColor, perfectColor);
					board[move] = null;
				}
			}
		}
	}
}
