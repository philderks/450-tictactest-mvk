package ch.bbw.m450.tictactoe.players;

import static org.assertj.core.api.Assertions.assertThat;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import java.util.List;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Provide;
import net.jqwik.api.Property;

class PerfectPlayerPropertyTest {

	@Property(tries = 100)
	void choosesLegalMoveWithoutChangingBoard(@ForAll("moveSequences") List<Integer> moves) {
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		var turn = Stone.CROSS;
		for (var move : moves) {
			board[move] = turn;
			if (TicTacToeMain.isWin(board, turn)) {
				board[move] = null;
				break;
			}
			turn = turn.opponent();
		}

		var original = board.clone();
		var choice = new PerfectPlayer().play(board, turn);
		assertThat(choice).isBetween(0, board.length - 1);
		assertThat(board[choice]).isNull();
		assertThat(board).containsExactly(original);
	}

	@Provide
	Arbitrary<List<Integer>> moveSequences() {
		return Arbitraries.integers().between(0, TicTacToeMain.BOARD_SIZE - 1)
				.list().uniqueElements().ofMinSize(0).ofMaxSize(TicTacToeMain.BOARD_SIZE - 1);
	}
}
