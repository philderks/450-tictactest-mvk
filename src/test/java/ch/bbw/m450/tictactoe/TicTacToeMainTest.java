package ch.bbw.m450.tictactoe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import ch.bbw.m450.tictactoe.players.GreedyPlayer;
import org.junit.jupiter.api.Test;

class TicTacToeMainTest {

	// helper: builds a board from a compact layout ('X' = CROSS, 'O' = CIRCLE, '.' = empty)
	private static Stone[] board(String layout) {
		var cells = layout.replaceAll("\\s", "");
		if (cells.length() != TicTacToeMain.BOARD_SIZE) {
			throw new IllegalArgumentException("board layout must have exactly 9 cells, got " + cells.length());
		}
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		for (var i = 0; i < cells.length(); i++) {
			board[i] = switch (cells.charAt(i)) {
				case 'X' -> Stone.CROSS;
				case 'O' -> Stone.CIRCLE;
				case '.' -> null;
				default -> throw new IllegalArgumentException("unexpected character '" + cells.charAt(i) + "'");
			};
		}
		return board;
	}

	// fixtures: named boards reused across the tests below
	private static final Stone[] ROW_WIN_CROSS = board("""
			XXX
			.O.
			O..
			""");

	private static final Stone[] DIAGONAL_WIN_CROSS = board("""
			O.X
			.X.
			X.O
			""");

	private static final Stone[] FULL_BOARD_NO_WINNER = board("""
			XOX
			XOO
			OXX
			""");

	@Test
	void isWin_detectsRowWin() {
		assertThat(TicTacToeMain.isWin(ROW_WIN_CROSS, Stone.CROSS)).isTrue();
		assertThat(TicTacToeMain.isWin(ROW_WIN_CROSS, Stone.CIRCLE)).isFalse();
	}

	@Test
	void isWin_detectsDiagonalWin() {
		assertThat(TicTacToeMain.isWin(DIAGONAL_WIN_CROSS, Stone.CROSS)).isTrue();
	}

	@Test
	void isWin_returnsFalseForNonWinningBoard() {
		assertThat(TicTacToeMain.isWin(FULL_BOARD_NO_WINNER, Stone.CROSS)).isFalse();
		assertThat(TicTacToeMain.isWin(FULL_BOARD_NO_WINNER, Stone.CIRCLE)).isFalse();
	}

	@Test
	void play_throwsIllegalArgumentException_whenSamePlayerInstanceUsedForBothSides() {
		var player = new GreedyPlayer();

		assertThatThrownBy(() -> TicTacToeMain.play(player, player))
				.isInstanceOf(IllegalArgumentException.class);
	}

	@Test
	void play_withTwoGreedyPlayers_producesDeterministicCrossWin() {
		// GreedyPlayer always fills the first free field: X takes 0,2,4,6 and
		// wins via the 2-4-6 anti-diagonal before O gets to move a 4th time.
		var winner = TicTacToeMain.play(new GreedyPlayer(), new GreedyPlayer());

		assertThat(winner).isEqualTo(Stone.CROSS);
	}
}
