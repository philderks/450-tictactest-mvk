package ch.bbw.m450.tictactoe;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import ch.bbw.m450.tictactoe.players.GreedyPlayer;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class TicTacToeMainTest {

	// fixtures: named boards reused across the tests below
	private static final Stone[] ROW_WIN_CROSS = {
			Stone.CROSS, Stone.CROSS, Stone.CROSS,
			null, Stone.CIRCLE, null,
			Stone.CIRCLE, null, null
	};

	private static final Stone[] DIAGONAL_WIN_CROSS = {
			Stone.CIRCLE, null, Stone.CROSS,
			null, Stone.CROSS, null,
			Stone.CROSS, null, Stone.CIRCLE
	};

	private static final Stone[] FULL_BOARD_NO_WINNER = {
			Stone.CROSS, Stone.CIRCLE, Stone.CROSS,
			Stone.CROSS, Stone.CIRCLE, Stone.CIRCLE,
			Stone.CIRCLE, Stone.CROSS, Stone.CROSS
	};

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

	@ParameterizedTest(name = "positions {0} won by {1}")
	@MethodSource("winningLines")
	void isWin_detectsAllWinningLines(int[] positions, Stone color) {
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		for (var position : positions) {
			board[position] = color;
		}

		assertThat(TicTacToeMain.isWin(board, color)).isTrue();
	}

	private static Stream<Arguments> winningLines() {
		return Stream.of(
				// rows
				Arguments.of(new int[]{0, 1, 2}, Stone.CROSS),
				Arguments.of(new int[]{3, 4, 5}, Stone.CIRCLE),
				Arguments.of(new int[]{6, 7, 8}, Stone.CROSS),
				// columns
				Arguments.of(new int[]{0, 3, 6}, Stone.CIRCLE),
				Arguments.of(new int[]{1, 4, 7}, Stone.CROSS),
				Arguments.of(new int[]{2, 5, 8}, Stone.CIRCLE),
				// diagonals
				Arguments.of(new int[]{0, 4, 8}, Stone.CROSS),
				Arguments.of(new int[]{2, 4, 6}, Stone.CIRCLE)
		);
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
